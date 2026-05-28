"""
extraction.py — LLM-powered parameter extraction with real PDF citation coordinates.

Fixes in this version:
  1. Bracket-depth JSON extractor — handles Cohere preamble text before JSON array.
     The old greedy regex failed when Cohere adds "Here are the results:" before the JSON.
  2. Batched extraction (all params in one LLM call) unchanged from previous version.
  3. Embedding dim guard unchanged.
  4. PDF spatial coordinates unchanged.
"""
from __future__ import annotations

import io
import json
import re
import sys
from typing import Any, Dict, List, Optional

from app.config import settings
from app.services import embeddings as emb
from app.services.llm import azure_llm

_BATCH_SIZE = 12


# ── JSON extraction helpers ───────────────────────────────────────────────────

def _strip_fences(raw: str) -> str:
    """Remove ```json … ``` or ``` … ``` wrappers."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    return raw.strip()


def _bracket_extract(text: str) -> str:
    """
    Finds the first '[' or '{' in text and returns the complete balanced
    JSON value by tracking bracket depth.

    This correctly handles Cohere responses that start with preamble text like:
    "Here are the extracted parameters:\n\n[{...}]"

    The old re.search(r"(\[[\s\S]*\])") approach failed because re.search
    returns the FIRST match, but with a greedy .* the match boundaries can
    be ambiguous when the engine backtracks on complex nested JSON.
    Bracket-depth tracking is O(n) and unambiguous.
    """
    open_char = None
    start = -1
    for i, ch in enumerate(text):
        if ch in ('[', '{'):
            open_char = ch
            start = i
            break

    if start == -1:
        return text  # no JSON structure found, return as-is

    close_char = ']' if open_char == '[' else '}'
    depth = 0
    in_string = False
    escape_next = False

    for i in range(start, len(text)):
        ch = text[i]
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
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
                return text[start:i + 1]

    # Unbalanced — return from start to end
    return text[start:]


def _safe_parse_json(raw: str) -> Any:
    """
    Parse JSON with three fallback strategies:
    1. Direct parse after stripping markdown fences.
    2. Bracket-depth extraction then parse (handles Cohere preamble).
    3. Return None on failure.
    """
    if not raw:
        return None

    # Strategy 1: strip fences + direct parse
    cleaned = _strip_fences(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Strategy 2: bracket-depth extraction
    extracted = _bracket_extract(cleaned)
    try:
        return json.loads(extracted)
    except json.JSONDecodeError:
        pass

    # Strategy 3: try the raw text as-is (last resort)
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        return None


# ── LLM batch extraction ──────────────────────────────────────────────────────

async def _llm_extract_batch(
    document_text: str,
    rules: List[Dict[str, Any]],
) -> List[Dict[str, Optional[str]]]:
    """
    Single LLM call to extract all parameters in `rules` from `document_text`.
    Returns list aligned with `rules`: [{"value": str|None, "citation": str|None}, ...]
    """
    doc_snippet = document_text[:14_000]
    count = len(rules)

    param_list_lines = []
    for i, rule in enumerate(rules):
        head = (rule.get("parameter_head") or "").strip()
        name = (rule.get("parameter_name") or head).strip()
        logic = (rule.get("parameter_logic") or "").strip()
        hint = f" (hint: {logic})" if logic else ""
        param_list_lines.append(
            f'{i + 1}. parameter_head="{head}", parameter_name="{name}"{hint}'
        )

    param_list_str = "\n".join(param_list_lines)

    system_prompt = (
        "You are a precise contract analysis assistant. "
        "Extract requested parameters from the contract text. "
        "You MUST respond with ONLY a valid JSON array — absolutely no prose, "
        "no markdown code fences, no explanations before or after. "
        f"The array MUST contain exactly {count} objects in the same order as the input list. "
        "Each object MUST have exactly these keys: "
        '  "param_name": string (copy the parameter_name from input), '
        '  "value": string or null (the extracted answer), '
        '  "citation": string or null (exact sentence from the contract that supports the value). '
        "If a parameter is not present in the contract, set both value and citation to null. "
        "Do NOT invent information not present in the text."
    )

    user_prompt = (
        f"Contract text (may be truncated):\n{doc_snippet}\n\n"
        f"Extract the following {count} parameters:\n{param_list_str}\n\n"
        f"Respond with a JSON array of exactly {count} objects. "
        "Start your response directly with '[' — no preamble text."
    )

    try:
        raw = await azure_llm.get_chat_completion(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format=None,   # Don't pass — Cohere ignores/breaks on this
            temperature=0.0,
            max_tokens=1200 + (count * 80),
        )
    except Exception as exc:
        print(f"[Extraction] Batch LLM call failed: {exc}", file=sys.stderr)
        return [{"value": None, "citation": None}] * count

    parsed = _safe_parse_json(raw)

    if not isinstance(parsed, list):
        print(
            f"[Extraction] Expected JSON array, got {type(parsed).__name__}. "
            f"Raw (first 400 chars): {(raw or '')[:400]}",
            file=sys.stderr,
        )
        # One more attempt: maybe LLM returned a single object instead of array
        if isinstance(parsed, dict):
            parsed = [parsed]
        else:
            return [{"value": None, "citation": None}] * count

    results: List[Dict[str, Optional[str]]] = []
    for i in range(count):
        try:
            item = parsed[i] if i < len(parsed) else {}
            if not isinstance(item, dict):
                item = {}
            results.append({
                "value": item.get("value") or None,
                "citation": item.get("citation") or None,
            })
        except Exception:
            results.append({"value": None, "citation": None})

    while len(results) < count:
        results.append({"value": None, "citation": None})

    return results


# ── Citation → char offset mapping ───────────────────────────────────────────

def _find_citation_offsets(document_text: str, citation: str) -> tuple[int, int]:
    if not citation or not document_text:
        return 0, 0
    idx = document_text.find(citation)
    if idx != -1:
        return idx, idx + len(citation)
    idx = document_text.lower().find(citation.lower())
    if idx != -1:
        return idx, idx + len(citation)
    for length in range(len(citation) - 10, 20, -10):
        fragment = citation[:length].strip()
        if not fragment:
            continue
        idx = document_text.lower().find(fragment.lower())
        if idx != -1:
            return idx, idx + len(fragment)
    return 0, 0


# ── PDF spatial coordinates ───────────────────────────────────────────────────

def _extract_pdf_spatial(file_bytes: bytes, citation: str) -> Optional[Dict[str, Any]]:
    if not file_bytes or not citation:
        return None
    try:
        import pdfplumber  # type: ignore
    except ImportError:
        return None

    citation_words = citation.lower().split()
    if not citation_words:
        return None

    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                page_text = (page.extract_text() or "").lower()
                if citation_words[0] not in page_text:
                    continue
                words = page.extract_words()
                word_texts = [w["text"].lower() for w in words]
                for i in range(len(word_texts)):
                    if word_texts[i] == citation_words[0]:
                        match_len = sum(
                            1 for j, cw in enumerate(citation_words)
                            if i + j < len(word_texts) and word_texts[i + j] == cw
                        )
                        if match_len >= max(1, len(citation_words) // 2):
                            matched = words[i: i + match_len]
                            return {
                                "page": page_num,
                                "rects": [[
                                    min(w["x0"] for w in matched),
                                    min(w["top"] for w in matched),
                                    max(w["x1"] for w in matched),
                                    max(w["bottom"] for w in matched),
                                ]],
                                "page_width": float(page.width),
                                "page_height": float(page.height),
                            }
    except Exception as exc:
        print(f"[PDF Spatial] pdfplumber error: {exc}", file=sys.stderr)
    return None


# ── Embed helper with dim guard ───────────────────────────────────────────────

def _safe_embed(text: str) -> Optional[List[float]]:
    if not text or not text.strip():
        return None
    vec = emb.embed(text)
    if vec is None:
        return None
    if len(vec) != settings.embedding_vector_dim:
        print(
            f"[Extraction] WARNING: embedding model returned {len(vec)}-dim vector "
            f"but EMBEDDING_VECTOR_DIM={settings.embedding_vector_dim}. "
            "Update your .env to match. Storing None to avoid DB errors.",
            file=sys.stderr,
        )
        return None
    return vec


# ── Main extraction engine ────────────────────────────────────────────────────

class ExtractionEngine:
    async def run_extraction_for_rules(
        self,
        document_text: str,
        rules: List[Dict[str, Any]],
        file_bytes: Optional[bytes] = None,
        content_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not rules:
            return []

        is_pdf = (content_type == "application/pdf") or bool(
            file_bytes and file_bytes[:4] == b"%PDF"
        )

        all_results: List[Dict[str, Any]] = []

        for batch_start in range(0, len(rules), _BATCH_SIZE):
            batch = rules[batch_start: batch_start + _BATCH_SIZE]
            llm_results = await _llm_extract_batch(document_text, batch)

            for rule, llm_item in zip(batch, llm_results):
                param_head = (rule.get("parameter_head") or "").strip()
                param_name = (rule.get("parameter_name") or param_head).strip()
                param_logic = (rule.get("parameter_logic") or "").strip()

                value = llm_item["value"]
                citation = llm_item["citation"]

                if not value:
                    all_results.append({
                        "header_name": param_head or "General",
                        "param_name": param_name,
                        "original_extract": None,
                        "user_override": None,
                        "match_score": 0.0,
                        "citation_text": None,
                        "citation_start": None,
                        "citation_end": None,
                        "spatial_json": None,
                        "vector_embed": None,
                        "source_query": param_logic or param_name,
                    })
                    continue

                start, end = _find_citation_offsets(document_text, citation or value)

                spatial: Optional[Dict[str, Any]] = None
                if is_pdf and file_bytes and citation:
                    spatial = _extract_pdf_spatial(file_bytes, citation)
                if spatial is None and start > 0:
                    spatial = {"page": 1, "rects": [[start, 0, end, 0]], "char_fallback": True}

                embed_vec = _safe_embed(citation or value)

                all_results.append({
                    "header_name": param_head or "General",
                    "param_name": param_name,
                    "original_extract": value,
                    "user_override": None,
                    "match_score": 1.0 if citation else 0.5,
                    "citation_text": citation,
                    "citation_start": start if start > 0 else None,
                    "citation_end": end if end > 0 else None,
                    "spatial_json": spatial,
                    "vector_embed": embed_vec,
                    "source_query": param_logic or param_name,
                })

        return all_results


extraction_engine = ExtractionEngine()