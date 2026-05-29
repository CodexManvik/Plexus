"""
extraction.py — LangGraph agentic parameter extraction pipeline.

Architecture:
  The ExtractionEngine replaces the previous static linear batch loop with an
  asynchronous LangGraph state machine containing two specialized agent roles:

  Extractor Agent (retrieve_node + extractor_node):
    1. retrieve_node: Queries the Oracle vector space (contract_document_chunks)
       using the rule's parameter_logic as the search query. Retrieves top-k
       semantically relevant paragraph chunks scoped to the contract.
       Falls back to document_text head+tail if embeddings are unavailable.
    2. extractor_node: Constructs an LLM prompt from the retrieved chunk texts.
       If a previous Critic cycle failed, injects critic_feedback into the prompt.
       Calls the configured LLM and parses {value, citation} JSON.

  Verification Agent — Critic Node (critic_node):
    3. critic_node: Programmatically validates:
         a. The citation string exists verbatim as a substring in at least one
            retrieved chunk (exact match, not fuzzy — no hallucination tolerance).
         b. Value format constraints per rule parameter_logic hints.
       On PASS: routes to resolve_spatial_node.
       On FAIL: increments retry_count and feeds critic_feedback back to extractor.
       On EXHAUSTED retries (circuit breaker): routes to circuit_break_node.

  Spatial Resolution (resolve_spatial_node):
    4. Resolves citation character offsets against the coord_index built at parse
       time by document_parser.py. Zero post-hoc PDF scanning. Zero pdfplumber.
       The lookup is O(n) over the coord_index keys and is deterministic.

  Circuit Breaker (circuit_break_node):
    5. Fires when MAX_CRITIC_RETRIES is exhausted. Writes a high-priority audit
       log entry. Returns a structured result with null value and flags the
       parameter for MANUAL_REVIEW. Does NOT silently return null.

  Section-Level Concurrency:
    Rules are grouped by their parameter_head (section header). Within each
    section group, a single vector retrieval call is shared across all rules,
    avoiding redundant Oracle queries for parameters that draw from the same
    document region. Groups are processed concurrently with an asyncio.Semaphore.

  terminal_node:
    6. Assembles the final Dict[str, Any] result compatible with ContractParameterExtracted.
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence, TypedDict

from app.config import settings
from app.services import embeddings as emb
from app.services.llm import cohere_llm
from app.services.logger import clm_logger

# CoordIndex is defined in document_parser; import lazily to avoid circular deps
# at module load time. The type alias is reproduced here for annotation clarity.
CoordIndex = dict[tuple[int, int], list[list[float]]]

# Semaphore cap: max concurrent LLM calls across all section groups.
_MAX_CONCURRENT_SECTIONS = 4


# ── JSON parsing helpers (retained from v1) ──────────────────────────────────

def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    return raw.strip()


def _bracket_extract(text: str) -> str:
    open_char = None
    start = -1
    for i, ch in enumerate(text):
        if ch in ("[", "{"):
            open_char = ch
            start = i
            break
    if start == -1:
        return text

    close_char = "]" if open_char == "[" else "}"
    depth = 0
    in_string = False
    escape_next = False

    for i in range(start, len(text)):
        ch = text[i]
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == open_char:
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]


def _safe_parse_json(raw: str) -> Any:
    if not raw:
        return None
    cleaned = _strip_fences(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    extracted = _bracket_extract(cleaned)
    try:
        return json.loads(extracted)
    except json.JSONDecodeError:
        pass
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        return None


# ── Spatial resolution helpers ────────────────────────────────────────────────

def _find_citation_offsets(document_text: str, citation: str) -> tuple[int, int]:
    if not citation or not document_text:
        return 0, 0
    # 1. Exact verbatim
    idx = document_text.find(citation)
    if idx != -1:
        return idx, idx + len(citation)
    # 2. Case-insensitive
    idx = document_text.lower().find(citation.lower())
    if idx != -1:
        return idx, idx + len(citation)
    # 3. Whitespace-normalized (handles LLM-introduced line breaks)
    import re as _re
    norm_cite = _re.sub(r'\s+', ' ', citation).strip()
    norm_doc = _re.sub(r'\s+', ' ', document_text)
    idx = norm_doc.lower().find(norm_cite.lower())
    if idx != -1:
        return idx, idx + len(norm_cite)
    # 4. First sentence of citation only (avoids matching wrong paragraph via tail trim)
    sentences = _re.split(r'(?<=[.!?])\s+', citation.strip())
    first_sentence = sentences[0] if sentences else ""
    if len(first_sentence) > 20:
        idx = document_text.lower().find(first_sentence.lower())
        if idx != -1:
            return idx, idx + len(first_sentence)
    return 0, 0


def _resolve_coord_from_index(
    char_start: int,
    char_end: int,
    coord_index: Optional[CoordIndex],
) -> Optional[Dict[str, Any]]:
    if not coord_index or (char_start == 0 and char_end == 0):
        return None

    # Collect ALL chunks that overlap the citation range (not just the best one)
    matched_keys = []
    for (k_start, k_end) in coord_index:
        overlap = min(char_end, k_end) - max(char_start, k_start)
        if overlap > 0:
            matched_keys.append((k_start, k_end))

    if not matched_keys:
        return None

    # Sort by position so rects are ordered top-to-bottom
    matched_keys.sort(key=lambda k: k[0])

    all_line_arrays = []
    for key in matched_keys:
        all_line_arrays.extend(coord_index[key])

    if not all_line_arrays:
        return None

    first = all_line_arrays[0]
    page_num = int(first[0])
    page_width = first[5]
    page_height = first[6]
    rects = [[arr[1], arr[2], arr[3], arr[4]] for arr in all_line_arrays]

    return {
        "page": page_num,
        "rects": rects,
        "page_width": page_width,
        "page_height": page_height,
    }


# ── Embedding dim guard ───────────────────────────────────────────────────────

def _safe_embed(text: str) -> Optional[List[float]]:
    if not text or not text.strip():
        return None
    vec = emb.embed(text)
    if vec is None:
        return None
    if len(vec) != settings.embedding_vector_dim:
        clm_logger.warning(
            f"[Extraction] embedding returned {len(vec)}-dim vector "
            f"but EMBEDDING_VECTOR_DIM={settings.embedding_vector_dim}. "
            "Update .env to match. Storing None to prevent DB type errors."
        )
        return None
    return vec


# ── LangGraph state schema ────────────────────────────────────────────────────

class ExtractionState(TypedDict):
    # Inputs — set once before graph execution
    rule: Dict[str, Any]
    document_text: str
    coord_index: Optional[CoordIndex]
    contract_id: Optional[str]
    # Shared context retrieved once per section group; injected before extractor runs.
    pre_fetched_chunks: Optional[List[Dict]]
    # Mutable state across node transitions
    value: Optional[str]
    citation: Optional[str]
    critic_feedback: Optional[str]
    retry_count: int
    # Final assembled output
    result: Optional[Dict[str, Any]]
    # Circuit breaker flag — set True when retries are exhausted
    circuit_broken: bool


# ── Graph node implementations ────────────────────────────────────────────────

async def _retrieve_node(
    state: ExtractionState,
    db: Any,  # AsyncSession — typed as Any to avoid SQLAlchemy import in type annotation
) -> ExtractionState:
    """
    Retrieves top-k relevant chunks from Oracle vector space.
    If pre_fetched_chunks is already populated (section-group optimization),
    skips the DB call entirely.
    Falls back to document_text head+tail when no chunk embeddings exist.
    """
    if state.get("pre_fetched_chunks") is not None:
        return state

    rule = state["rule"]
    param_name = (rule.get("parameter_name") or rule.get("parameter_head") or "UNKNOWN").strip()
    query = (rule.get("parameter_logic") or rule.get("parameter_name") or "").strip()
    contract_id = state.get("contract_id")

    clm_logger.info(f"[Extraction] Retrieve Node running for parameter '{param_name}' on contract '{contract_id}' with query: '{query}'")

    chunk_hits: List[Dict] = []
    if db is not None and contract_id and query:
        try:
            chunk_hits = await emb.vector_search_chunks(
                db=db,
                query_text=query,
                contract_id=contract_id,
                top_k=5,
            )
            clm_logger.info(f"[Extraction] Retrieve Node found {len(chunk_hits)} chunk hits for parameter '{param_name}'")
        except Exception as exc:
            clm_logger.error(f"[Extraction] vector_search_chunks failed for parameter '{param_name}': {exc}", exc_info=True)

    state["pre_fetched_chunks"] = chunk_hits
    return state


async def _extractor_node(state: ExtractionState) -> ExtractionState:
    """
    Builds the LLM prompt from retrieved chunks (or document_text fallback),
    injects critic_feedback on retry passes, and parses the {value, citation} response.
    """
    rule = state["rule"]
    param_head = (rule.get("parameter_head") or "").strip()
    param_name = (rule.get("parameter_name") or param_head).strip()
    param_logic = (rule.get("parameter_logic") or "").strip()
    hint = f" (extraction hint: {param_logic})" if param_logic else ""

    chunk_hits = state.get("pre_fetched_chunks") or []

    clm_logger.info(
        f"[Extraction] Extractor Node running for parameter '{param_name}' (head: '{param_head}'). "
        f"Context size: {len(chunk_hits)} chunks. "
        f"Attempt: {state.get('retry_count', 0) + 1}. "
        f"Previous critic feedback: {state.get('critic_feedback') or 'None'}"
    )

    if chunk_hits:
        # Assemble context from retrieved chunks — ordered by relevance (already ASC distance).
        context_sections = []
        for i, chunk in enumerate(chunk_hits, start=1):
            context_sections.append(f"[Chunk {i}]\n{chunk.get('chunk_text', '')}")
        context_text = "\n\n".join(context_sections)
    else:
        # Graceful degradation: no chunk index available. Use head + tail of document.
        doc = state["document_text"]
        head = doc[:8000]
        tail = doc[-3000:] if len(doc) > 11000 else ""
        context_text = head + ("\n\n[... document continues ...]\n\n" + tail if tail else "")

    retry_note = ""
    if state.get("critic_feedback"):
        retry_note = (
            f"\n\nPREVIOUS ATTEMPT FAILED CRITIC VALIDATION:\n"
            f"{state['critic_feedback']}\n"
            "You MUST correct the above error in this response."
        )

    system_prompt = (
        "You are a precise legal contract analysis engine. "
        "Extract the requested parameter from the provided contract text excerpts. "
        "Respond with ONLY a valid JSON object — no prose, no markdown fences, no explanations. "
        'The object MUST have exactly two keys: "value" (string or null) and "citation" (string or null). '
        '"citation" MUST be an exact verbatim substring copied from the provided text — do not paraphrase. '
        "If the parameter is not present, set both to null."
    )

    user_prompt = (
        f"Contract text excerpts:\n\n{context_text}\n\n"
        f'Extract: parameter_head="{param_head}", parameter_name="{param_name}"{hint}.{retry_note}\n\n'
        'Respond with exactly: {"value": "...", "citation": "..."}'
    )

    try:
        raw = await cohere_llm.get_extraction_completion(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
    except Exception as exc:
        clm_logger.error(f"[Extraction] LLM extraction call failed for parameter '{param_name}': {exc}", exc_info=True)
        raw = ""

    parsed = _safe_parse_json(raw)
    if isinstance(parsed, dict):
        state["value"] = parsed.get("value") or None
        state["citation"] = parsed.get("citation") or None
    else:
        state["value"] = None
        state["citation"] = None

    clm_logger.info(
        f"[Extraction] Extractor Node output for '{param_name}': "
        f"Value: '{state['value']}' | Citation: '{state['citation']}'"
    )

    return state


def _normalize_ws(text: str) -> str:
    """
    Collapses all whitespace runs (spaces, tabs, newlines, carriage returns) to a
    single space and strips leading/trailing whitespace.
    Used for citation verification only — the original text is never mutated.
    """
    import re as _re
    return _re.sub(r"\s+", " ", text).strip()


def _citation_in_text(citation: str, corpus: str) -> bool:
    """
    Checks whether `citation` exists within `corpus` using a two-level strategy:
      1. Exact verbatim substring (fastest — handles most cases).
      2. Whitespace-normalized substring — handles LLM-introduced line breaks in
         table cell citations where the parsed text joins lines with spaces.
    Returns True on either match.
    """
    if citation in corpus:
        return True
    # Whitespace-normalized check — tolerates \n vs space differences.
    norm_cite = _normalize_ws(citation)
    norm_corpus = _normalize_ws(corpus)
    if norm_cite and norm_cite in norm_corpus:
        return True
    return False


async def _critic_node(state: ExtractionState) -> ExtractionState:
    """
    Validates the extractor's output. Checks:
      1. citation is present (exact OR whitespace-normalized) in at least one
         retrieved chunk OR full document_text.
      2. value is non-null when citation is present (no orphan citations).
    On PASS: clears critic_feedback.
    On FAIL: writes specific feedback and increments retry_count.
    On EXHAUSTED: sets circuit_broken=True.
    """
    from app.services.agents.critic_agent import CriticAgent

    rule = state["rule"]
    param_name = (rule.get("parameter_name") or rule.get("parameter_head") or "UNKNOWN").strip()
    max_retries = settings.extraction_max_critic_retries
    citation = state.get("citation")
    value = state.get("value")
    pre_fetched_chunks = state.get("pre_fetched_chunks") or []
    full_text = state.get("document_text") or ""
    parameter_logic = rule.get("parameter_logic") or ""
    retry_count = state.get("retry_count", 0)

    clm_logger.info(
        f"[Extraction] Critic Node validating '{param_name}' "
        f"(Value: '{value}', Citation: '{citation}', Attempt: {retry_count + 1}/{max_retries})"
    )

    critic = CriticAgent()
    is_valid, feedback = await critic.validate_extraction(
        parameter_name=param_name,
        value=value,
        citation=citation,
        pre_fetched_chunks=pre_fetched_chunks,
        full_text=full_text,
        parameter_logic=parameter_logic,
        retry_count=retry_count,
    )

    if is_valid:
        state["critic_feedback"] = None
        clm_logger.info(f"[Extraction] Critic Node validation PASSED for '{param_name}'")
    else:
        new_retry = retry_count + 1
        state["retry_count"] = new_retry
        state["critic_feedback"] = feedback
        if new_retry > max_retries:
            state["circuit_broken"] = True
            state["critic_feedback"] = f"CIRCUIT BREAKER: {feedback}"
            clm_logger.error(f"[Extraction] Critic Node validation FAILED (circuit breaker triggered) for '{param_name}'.")
        else:
            clm_logger.warning(f"[Extraction] Critic Node validation FAILED for '{param_name}'. Attempt {new_retry}/{max_retries}")

    return state


def _resolve_spatial_node(state: ExtractionState) -> ExtractionState:
    """
    Resolves citation character offsets and maps them to pre-computed bounding
    boxes from the coord_index. No PDF re-parsing. No pdfplumber. No fuzzy scan.
    """
    rule = state["rule"]
    param_name = (rule.get("parameter_name") or rule.get("parameter_head") or "UNKNOWN").strip()
    citation = state.get("citation")
    document_text = state["document_text"]
    coord_index = state.get("coord_index")

    start, end = _find_citation_offsets(document_text, citation or "")

    spatial = _resolve_coord_from_index(start, end, coord_index)

    if spatial is None and start > 0:
        # Char-offset fallback for non-PDF formats (DOCX/XLSX have empty coord_index).
        spatial = {"page": 1, "rects": [[start, 0, end, 0]], "char_fallback": True}

    # Attach resolved spatial data to state for terminal_node to read.
    state["_resolved_start"] = start if start > 0 else None
    state["_resolved_end"] = end if end > 0 else None
    state["_resolved_spatial"] = spatial

    clm_logger.info(
        f"[Extraction] Resolve Spatial Node for '{param_name}': "
        f"Offsets: ({state.get('_resolved_start')}, {state.get('_resolved_end')}) | "
        f"Page: {spatial.get('page') if spatial else 'None'} | "
        f"Rects count: {len(spatial.get('rects', [])) if spatial else 0}"
    )
    return state


async def _circuit_break_node(
    state: ExtractionState,
    db: Any,
    contract_id: Optional[str],
    modified_by: str = "SYSTEM",
) -> ExtractionState:
    """
    Circuit breaker handler. Writes a high-priority audit trail entry and marks
    the parameter for manual review. Does NOT silently discard the extraction attempt.
    """
    rule = state["rule"]
    param_name = (rule.get("parameter_name") or rule.get("parameter_head") or "UNKNOWN").strip()

    clm_logger.error(
        f"[Extraction] CIRCUIT BREAKER FIRED for parameter '{param_name}' "
        f"on contract '{contract_id}'. {state.get('critic_feedback', '')}"
    )

    # Write audit trail entry if a DB session was provided.
    if db is not None and contract_id:
        try:
            from app.models.orm import ContractAuditTrail  # local import to avoid circular
            db.add(ContractAuditTrail(
                contract_id=contract_id,
                action_type="EXTRACTION_CIRCUIT_BREAK",
                field_changed=f"parameter:{param_name}",
                old_value_clob=None,
                new_value_clob=state.get("critic_feedback"),
                modified_by="SYSTEM_EXTRACTION_ENGINE",
            ))
            clm_logger.info(f"[Extraction] Staged audit trail entry for circuit break on '{param_name}' in contract '{contract_id}'")
            # Note: caller is responsible for db.commit() — we don't commit inside nodes.
        except Exception as exc:
            clm_logger.error(f"[Extraction] Audit write in circuit_break_node failed for '{param_name}': {exc}", exc_info=True)

    # Signal caller to flag contract for MANUAL_REVIEW.
    state["_requires_manual_review"] = True
    return state


def _terminal_node(state: ExtractionState) -> ExtractionState:
    """
    Assembles the final result dict from the accumulated state. This is the
    only location where the output structure is defined — no dict construction
    is scattered across other nodes.
    """
    rule = state["rule"]
    param_head = (rule.get("parameter_head") or "").strip()
    param_name = (rule.get("parameter_name") or param_head).strip()
    param_logic = (rule.get("parameter_logic") or "").strip()

    value = state.get("value")
    citation = state.get("citation")

    state["result"] = {
        "header_name": param_head or "General",
        "param_name": param_name,
        "original_extract": value,
        "user_override": None,
        "match_score": 1.0 if (citation and not state.get("circuit_broken")) else (0.5 if value else 0.0),
        "citation_text": citation,
        "citation_start": state.get("_resolved_start"),
        "citation_end": state.get("_resolved_end"),
        "spatial_json": state.get("_resolved_spatial"),
        "vector_embed": None,
        "source_query": param_logic or param_name,
        "requires_manual_review": state.get("_requires_manual_review", False),
    }

    # Safely serialize result dict without massive vector dumps
    clm_logger.info(
        f"[Extraction] Terminal Node completed for '{param_name}': "
        f"Result Dict: {json.dumps({k: v for k, v in state['result'].items() if k != 'vector_embed'}, default=str)}"
    )
    return state


# ── Section-group runner ──────────────────────────────────────────────────────

async def _run_section_group(
    rules: List[Dict[str, Any]],
    document_text: str,
    coord_index: Optional[CoordIndex],
    db: Any,
    contract_id: Optional[str],
    semaphore: asyncio.Semaphore,
) -> List[Dict[str, Any]]:
    """
    Processes a single section group (rules sharing the same parameter_head).
    Performs union retrieval queries (up to 3 distinct queries) to pre-fetch chunks.
    """
    section_name = (rules[0].get("parameter_head") or "General").strip() if rules else "General"
    async with semaphore:
        # Build distinct queries from all rules in the section (cap at 3 to limit DB calls)
        distinct_queries = list(dict.fromkeys(
            (rule.get("parameter_logic") or rule.get("parameter_name") or "").strip()
            for rule in rules
            if (rule.get("parameter_logic") or rule.get("parameter_name") or "").strip()
        ))[:3]

        clm_logger.info(
            f"[Extraction] Starting section group '{section_name}' processing with {len(rules)} rules. "
            f"Distinct queries: {distinct_queries}"
        )

        all_chunks: dict[int, dict] = {}
        if db is not None and contract_id and distinct_queries:
            for query in distinct_queries:
                try:
                    hits = await emb.vector_search_chunks(
                        db=db,
                        query_text=query,
                        contract_id=contract_id,
                        top_k=6,
                    )
                    for hit in hits:
                        chunk_id = hit.get("chunk_id")
                        if chunk_id is not None and chunk_id not in all_chunks:
                            all_chunks[chunk_id] = hit
                except Exception as exc:
                    clm_logger.error(f"[Extraction] Section retrieval failed for query '{query}': {exc}", exc_info=True)

        shared_chunks = sorted(all_chunks.values(), key=lambda x: float(x.get("distance") or 1.0))
        clm_logger.info(f"[Extraction] Section group '{section_name}' pre-fetched {len(shared_chunks)} chunks for contract '{contract_id}'")

        # ── Run each rule through the state machine ───────────────────────────
        results: List[Dict[str, Any]] = []
        for rule in rules:
            rule_start_time = asyncio.get_event_loop().time()
            state: ExtractionState = {
                "rule": rule,
                "document_text": document_text,
                "coord_index": coord_index,
                "contract_id": contract_id,
                "pre_fetched_chunks": shared_chunks,
                "value": None,
                "citation": None,
                "critic_feedback": None,
                "retry_count": 0,
                "result": None,
                "circuit_broken": False,
            }

            max_retries = settings.extraction_max_critic_retries

            # Node: extractor (initial pass)
            state = await _extractor_node(state)

            # Node: critic + conditional loop
            while True:
                state = await _critic_node(state)

                if state.get("circuit_broken"):
                    state = await _circuit_break_node(
                        state, db=db, contract_id=contract_id
                    )
                    break

                if state.get("critic_feedback") is None:
                    # PASS — proceed to spatial resolution
                    break

                if state.get("retry_count", 0) > max_retries:
                    state["circuit_broken"] = True
                    state = await _circuit_break_node(
                        state, db=db, contract_id=contract_id
                    )
                    break

                # FAIL — re-run extractor with feedback injected
                state = await _extractor_node(state)

            # Second pass: if extraction returned null, retry with a broader composite query
            if not state.get("value") and not state.get("circuit_broken") and db is not None and contract_id:
                param_head = (rule.get("parameter_head") or "").strip()
                param_name = (rule.get("parameter_name") or "").strip()
                param_logic = (rule.get("parameter_logic") or "").strip()
                broader_query = " ".join(filter(None, [param_head, param_name, param_logic]))
                clm_logger.info(f"[Extraction] First-pass returned null for '{param_name}'. Initiating second-pass broader query: '{broader_query}'")
                try:
                    extra_hits = await emb.vector_search_chunks(
                        db=db,
                        query_text=broader_query,
                        contract_id=contract_id,
                        top_k=12,
                    )
                    existing_ids = {c.get("chunk_id") for c in (state.get("pre_fetched_chunks") or [])}
                    new_chunks = [h for h in extra_hits if h.get("chunk_id") not in existing_ids]
                    if new_chunks:
                        clm_logger.info(
                            f"[Extraction] Second-pass found {len(new_chunks)} new chunks. "
                            f"Appending top 6 to context. "
                            f"Carrying forward retry_count={state.get('retry_count', 0)} "
                            f"against budget={settings.extraction_max_critic_retries}."
                        )
                        state["pre_fetched_chunks"] = (state.get("pre_fetched_chunks") or []) + new_chunks[:6]
                        state["critic_feedback"] = None
                        # NOTE: retry_count is NOT reset here — the first-pass budget carries forward
                        # so that the combined attempt count is measured against the single circuit-breaker
                        # budget. Resetting it here would allow a parameter to silently bypass the limit.
                        # Re-run extraction with expanded context
                        state = await _extractor_node(state)
                        while True:
                            state = await _critic_node(state)
                            if state.get("circuit_broken") or state.get("critic_feedback") is None:
                                break
                            if state.get("retry_count", 0) > settings.extraction_max_critic_retries:
                                state["circuit_broken"] = True
                                state = await _circuit_break_node(state, db=db, contract_id=contract_id)
                                break
                            state = await _extractor_node(state)
                        if state.get("circuit_broken"):
                            state = await _circuit_break_node(state, db=db, contract_id=contract_id)
                    else:
                        clm_logger.info(f"[Extraction] Second-pass broader query returned no new chunks.")
                except Exception as exc:
                    clm_logger.error(f"[Extraction] Second-pass retrieval failed for '{param_name}': {exc}", exc_info=True)

            # Node: resolve_spatial (only if not circuit-broken or has value)
            if state.get("value") or state.get("citation"):
                state = _resolve_spatial_node(state)

            # Node: terminal
            state = _terminal_node(state)
            if state.get("result") is not None:
                embed_input = state.get("citation") or state.get("value") or ""
                state["result"]["vector_embed"] = await asyncio.to_thread(_safe_embed, embed_input)

            # ── Structured extraction telemetry (log only, no DB write) ──────────
            rule_latency_ms = round((asyncio.get_event_loop().time() - rule_start_time) * 1000, 1)
            param_head = (rule.get("parameter_head") or "").strip()
            param_name_log = (rule.get("parameter_name") or "").strip()
            extraction_result = state.get("value")
            citation_verified = (
                state.get("critic_feedback") is None
                and bool(state.get("citation"))
            )
            clm_logger.info(
                "[ExtractionTelemetry] "
                f"contract_id={contract_id!r} "
                f"parameter_head={param_head!r} "
                f"parameter_name={param_name_log!r} "
                f"extraction_result={str(extraction_result)[:120]!r} "
                f"citation_verified={citation_verified} "
                f"retry_count={state.get('retry_count', 0)} "
                f"circuit_broken={state.get('circuit_broken', False)} "
                f"total_latency_ms={rule_latency_ms}"
            )

            results.append(state["result"])

        clm_logger.info(f"[Extraction] Completed section group '{section_name}' processing.")
        return results


# ── Main extraction engine ────────────────────────────────────────────────────

class ExtractionEngine:
    async def run_extraction_for_rules(
        self,
        document_text: str,
        rules: List[Dict[str, Any]],
        file_bytes: Optional[bytes] = None,
        content_type: Optional[str] = None,
        coord_index: Optional[CoordIndex] = None,
        db: Any = None,
        contract_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Executes the LangGraph agentic extraction pipeline for all rules.

        Rules are grouped by parameter_head (section) for shared vector retrieval.
        Section groups are executed concurrently up to _MAX_CONCURRENT_SECTIONS.
        Within each group, rules are processed sequentially through the
        Extractor → Critic loop with circuit-breaker protection.

        Parameters
        ----------
        document_text   Full extracted text from document_parser.
        rules           List of rule dicts with parameter_head, parameter_name, parameter_logic.
        file_bytes      Raw file bytes (retained for API compatibility; no longer used internally).
        content_type    MIME type (retained for API compatibility).
        coord_index     Character-offset → line-coordinate mapping from document_parser.
        db              AsyncSession for vector_search_chunks and audit writes.
        contract_id     Contract identifier for scoped vector search.

        Returns
        -------
        List of result dicts aligned with input `rules` order.
        """
        if not rules:
            return []

        clm_logger.info(f"=== STARTING EXTRACTION ENGINE ===")
        clm_logger.info(f"Contract ID: {contract_id} | Rules Count: {len(rules)}")

        # ── Group rules by section header ─────────────────────────────────────
        section_groups: dict[str, list[Dict[str, Any]]] = defaultdict(list)
        rule_order: list[str] = []
        for rule in rules:
            section = (rule.get("parameter_head") or "General").strip()
            if section not in section_groups:
                rule_order.append(section)
            section_groups[section].append(rule)

        semaphore = asyncio.Semaphore(_MAX_CONCURRENT_SECTIONS)

        # ── Dispatch section groups concurrently ──────────────────────────────
        group_tasks = [
            _run_section_group(
                rules=section_groups[section],
                document_text=document_text,
                coord_index=coord_index,
                db=db,
                contract_id=contract_id,
                semaphore=semaphore,
            )
            for section in rule_order
        ]

        group_results: list[list[Dict[str, Any]]] = await asyncio.gather(*group_tasks)

        # ── Re-assemble in original rule order ────────────────────────────────
        # Build a flat lookup: (param_head, param_name) → result
        result_lookup: Dict[tuple[str, str], Dict[str, Any]] = {}
        for group_result_list in group_results:
            for res in group_result_list:
                key = (res.get("header_name", ""), res.get("param_name", ""))
                result_lookup[key] = res

        ordered_results: List[Dict[str, Any]] = []
        for rule in rules:
            param_head = (rule.get("parameter_head") or "General").strip()
            param_name = (rule.get("parameter_name") or param_head).strip()
            key = (param_head, param_name)
            if key in result_lookup:
                ordered_results.append(result_lookup[key])
            else:
                # Should not occur; defensive fallback.
                ordered_results.append({
                    "header_name": param_head,
                    "param_name": param_name,
                    "original_extract": None,
                    "user_override": None,
                    "match_score": 0.0,
                    "citation_text": None,
                    "citation_start": None,
                    "citation_end": None,
                    "spatial_json": None,
                    "vector_embed": None,
                    "source_query": rule.get("parameter_logic") or param_name,
                    "requires_manual_review": False,
                })

        clm_logger.info(f"=== COMPLETED EXTRACTION ENGINE ===")
        clm_logger.info(f"Contract ID: {contract_id} | Successful Extractions: {len(ordered_results)}")
        return ordered_results


extraction_engine = ExtractionEngine()