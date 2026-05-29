"""
contracts.py — key changes from original:

1. file_bytes stored in document_blob (raw PDF/DOCX persisted for viewer).
2. extract_document_text now returns (text, coord_index) — callers unpack the tuple.
3. _build_and_store_chunks: layout-driven paragraph chunking with batch embed.
4. document_vector computed as mean-pool across all chunk vectors (not first-5k-chars).
5. ExtractionEngine receives coord_index, db, and contract_id for agentic RAG pipeline.
6. _classify_and_inject_rules: LLM auto-classification for unknown contract types.
   Generated rules staged in master_extraction_rules with is_active=False.
7. Contracts with circuit-breaker exhaustion are flagged MANUAL_REVIEW in workflow_state.
8. New endpoint GET /{contract_id}/document — serves the raw file.
9. SQLite references removed.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import numpy as np

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models.orm import (
    ContractAuditTrail,
    ContractDocumentChunk,
    ContractMaster,
    ContractParameterExtracted,
    MasterExtractionRule,
    MetadataOption,
    ContractTagSuggestion,
)
from app.schemas.pydantic_models import (
    AuditTrailResponse,
    ContractListResponse,
    ContractResponse,
    ContractSearchResponse,
    DynamicSearchAddRequest,
    ExtractionStatusResponse,
    LockAcquireRequest,
    LockResponse,
    ParameterResponse,
    ParameterUpdateRequest,
    ParameterVerifyRequest,
    ReExtractionResponse,
    WorkflowActionRequest,
    SemanticSearchResult,
    SemanticSearchResponse,
    ContractTagSuggestionResponse,
    TagSuggestionsAcceptRequest,
    TagSuggestionsEditRequest,
    DraftPauseRequest,
    DraftPauseResponse,
)
from app.services.document_parser import CoordIndex, extract_document_text
from app.services.extraction import extraction_engine
from app.services import embeddings as emb
from app.services.embeddings import embed_batch
from app.services.logger import clm_logger
from app.services.publishing import publishing_service
from app.services.agents import TaggingAgent, GroundingAgent, CriticAgent, RiskAgent
from app.services.validation import ValidationService

router = APIRouter(prefix="/contracts", tags=["Contracts Workflow"])

tagging_agent = TaggingAgent()
risk_agent = RiskAgent()
validation_service = ValidationService()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _build_and_store_chunks(
    db: AsyncSession,
    contract_id: str,
    document_text: str,
    coord_index: CoordIndex,
) -> Optional[List[float]]:
    """
    Splits the document into paragraph-level chunks using the coord_index boundaries
    produced by the layout-aware parser. For each chunk:
      - Writes a ContractDocumentChunk row with spatial_json (per-line coordinates).
      - Computes the chunk embedding via embed_batch (single model.encode() call).

    Returns the mean-pooled document_vector across all chunk vectors, or None if
    embeddings are unavailable. This replaces the truncated 5,000-character document
    embedding with a representation of the entire document.
    """
    if not document_text:
        return None

    # Build ordered list of (start, end, spatial_json) from coord_index.
    # coord_index keys: (start_char, end_char) → [[page,x0,y0,x1,y1,pw,ph], ...]
    sorted_keys = sorted(coord_index.keys(), key=lambda k: k[0])

    chunk_records: List[Dict[str, Any]] = []
    if sorted_keys:
        for idx, (start, end) in enumerate(sorted_keys):
            chunk_text = document_text[start:end]
            if not chunk_text.strip():
                continue
            chunk_records.append({
                "chunk_index": idx,
                "chunk_text": chunk_text,
                "char_start": start,
                "char_end": end,
                "spatial_json": coord_index[(start, end)],
            })
    else:
        # Non-PDF path: coord_index is empty. Chunk the raw text at newline boundaries.
        raw_chunks = [c.strip() for c in document_text.split("\n\n") if c.strip()]
        cursor = 0
        for idx, chunk_text in enumerate(raw_chunks):
            start = document_text.find(chunk_text, cursor)
            if start == -1:
                start = cursor
            end = start + len(chunk_text)
            chunk_records.append({
                "chunk_index": idx,
                "chunk_text": chunk_text,
                "char_start": start,
                "char_end": end,
                "spatial_json": None,
            })
            cursor = end

    if not chunk_records:
        return None

    # ── Batch embed all chunks in a single model call ─────────────────────────
    chunk_texts = [r["chunk_text"] for r in chunk_records]
    vectors: List[Optional[List[float]]] = await asyncio.to_thread(embed_batch, chunk_texts)

    # Load existing chunk indices to avoid hitting uq_chunk_contract_idx on re-runs
    existing_result = await db.execute(
        select(ContractDocumentChunk.chunk_index).where(
            ContractDocumentChunk.contract_id == contract_id
        )
    )
    existing_indices = {row[0] for row in existing_result.all()}

    # ── Persist chunk rows ────────────────────────────────────────────────────
    valid_vectors: List[List[float]] = []
    for record, vec in zip(chunk_records, vectors):
        # Dim guard: discard mismatched vectors to prevent Oracle type errors.
        if vec is not None and len(vec) == settings.embedding_vector_dim:
            valid_vectors.append(vec)
            store_vec = emb.quantize_to_int8(vec)
        else:
            store_vec = None

        if record["chunk_index"] not in existing_indices:
            db.add(ContractDocumentChunk(
                contract_id=contract_id,
                chunk_index=record["chunk_index"],
                chunk_text=record["chunk_text"],
                char_start=record["char_start"],
                char_end=record["char_end"],
                spatial_json=record["spatial_json"],
                chunk_vector=store_vec,
                embed_model_name=settings.sentence_transformer_model,
                embed_dimension=settings.embedding_vector_dim,
                embed_quant_type="INT8",
                parser_version=settings.parser_version,
                chunking_version=settings.chunking_version,
            ))

    if not valid_vectors:
        return None

    # ── Mean-pool document_vector across all chunk vectors ────────────────────
    vector_matrix = np.array(valid_vectors, dtype=np.float32)
    mean_vector: np.ndarray = vector_matrix.mean(axis=0)
    # Re-normalize after averaging to restore unit-length for cosine search.
    norm = np.linalg.norm(mean_vector)
    if norm > 0:
        mean_vector = mean_vector / norm
    return mean_vector.tolist()


async def _classify_and_inject_rules(
    document_text: str,
    submitted_contract_type: str,
    submitted_agreement_type: str,
    db: AsyncSession,
    contract_id: str,
) -> tuple[str, str, List[Dict[str, Any]]]:
    """
    Invoked when zero MasterExtractionRule rows match (contract_type, agreement_type).

    Calls the LLM with the first 6,000 chars of the document to:
      1. Confirm or correct the contract_type and agreement_type.
      2. Generate a list of parameter extraction rules as a JSON payload.

    Generated rules are written to master_extraction_rules with:
      - is_active = False   (staged, not yet active)
      - created_by = 'SYSTEM_AI_PROPOSAL'
    This builds an administrator review queue. The rules are also returned
    as transient payloads for immediate use in the current upload.

    Returns: (resolved_contract_type, resolved_agreement_type, transient_rule_payloads)
    """
    from app.services.llm import cohere_llm
    import json as _json

    clm_logger.info(
        f"[Classification] Starting auto-classification for contract '{contract_id}' "
        f"(submitted_contract_type: '{submitted_contract_type}', submitted_agreement_type: '{submitted_agreement_type}')"
    )

    doc_head = document_text[:6000]

    system_prompt = (
        "You are a contract classification and parameter schema generator. "
        "Given a contract document excerpt, output a single valid JSON object with these keys: "
        '"contract_type" (string, UPPER_SNAKE_CASE), '
        '"agreement_type" (string, UPPER_SNAKE_CASE), '
        '"rules" (array of objects, each with: "parameter_head" string, "parameter_name" string, '
        '"parameter_logic" string describing where/how to extract the value). '
        "Output ONLY valid JSON — no prose, no fences."
    )
    user_prompt = (
        f"Submitted contract_type: {submitted_contract_type}\n"
        f"Submitted agreement_type: {submitted_agreement_type}\n\n"
        f"Document excerpt:\n{doc_head}\n\n"
        "Classify this contract and generate 8–15 extraction rules covering all critical "
        "legal and commercial parameters. Respond with the JSON object only."
    )

    resolved_ct = submitted_contract_type
    resolved_at = submitted_agreement_type
    transient_rules: List[Dict[str, Any]] = []

    try:
        raw = await cohere_llm.get_chat_completion(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format=None,
            temperature=0.0,
            max_tokens=2000,
        )
    except Exception as exc:
        clm_logger.error(f"[Classification] LLM call failed for contract '{contract_id}': {exc}", exc_info=True)
        return resolved_ct, resolved_at, transient_rules

    if not raw.strip():
        clm_logger.warning(f"[Classification] LLM returned empty response — skipping auto-classification for contract '{contract_id}'")
        return resolved_ct, resolved_at, transient_rules

    # Import the JSON parser from extraction to avoid code duplication.
    from app.services.extraction import _safe_parse_json
    parsed = _safe_parse_json(raw)

    if not isinstance(parsed, dict):
        clm_logger.warning(
            f"[Classification] LLM response is not a valid JSON dictionary: {type(parsed).__name__} for contract '{contract_id}'. "
            f"Raw (first 300 chars): {raw[:300]}"
        )
        return resolved_ct, resolved_at, transient_rules

    resolved_ct = (parsed.get("contract_type") or submitted_contract_type).strip().upper()
    resolved_at = (parsed.get("agreement_type") or submitted_agreement_type).strip().upper()
    raw_rules = parsed.get("rules") or []

    clm_logger.info(
        f"[Classification] Contract '{contract_id}' successfully auto-classified to: "
        f"contract_type='{resolved_ct}', agreement_type='{resolved_at}'. Generated {len(raw_rules)} staged rules."
    )

    # ── Stage generated rules in master_extraction_rules ─────────────────────
    staged_count = 0
    for rule_def in raw_rules:
        if not isinstance(rule_def, dict):
            continue
        p_head = (rule_def.get("parameter_head") or "General").strip()
        p_name = (rule_def.get("parameter_name") or "").strip()
        p_logic = (rule_def.get("parameter_logic") or "").strip()
        if not p_name:
            continue

        transient_rules.append({
            "parameter_head": p_head,
            "parameter_name": p_name,
            "parameter_logic": p_logic,
        })

        # Check for existing rule with this signature before inserting.
        existing = await db.execute(
            select(MasterExtractionRule).where(
                and_(
                    MasterExtractionRule.contract_type == resolved_ct,
                    MasterExtractionRule.agreement_type == resolved_at,
                    MasterExtractionRule.parameter_head == p_head,
                    MasterExtractionRule.parameter_name == p_name,
                )
            )
        )
        if existing.scalars().first() is not None:
            continue  # Already staged or active — skip insertion.

        db.add(MasterExtractionRule(
            contract_type=resolved_ct,
            agreement_type=resolved_at,
            parameter_head=p_head,
            parameter_name=p_name,
            parameter_logic=p_logic[:250] if p_logic else None,
            is_active=False,         # Staged — requires admin activation.
            created_by="SYSTEM_AI_PROPOSAL",
        ))
        staged_count += 1

    await db.flush()  # Assign PKs without committing the parent transaction.

    # Write AI_RULES_STAGED audit event if any new rules were staged.
    if staged_count > 0:
        import json as _audit_json
        db.add(ContractAuditTrail(
            contract_id=contract_id,
            action_type="AI_RULES_STAGED",
            field_changed="master_extraction_rules",
            old_value_clob=None,
            new_value_clob=_audit_json.dumps({
                "staged_count": staged_count,
                "contract_type": resolved_ct,
                "agreement_type": resolved_at,
            }),
            modified_by="SYSTEM_AI_PROPOSAL",
        ))
        clm_logger.info(
            f"[Classification] AI_RULES_STAGED audit written for contract '{contract_id}': "
            f"{staged_count} rules staged for contract_type='{resolved_ct}', "
            f"agreement_type='{resolved_at}'."
        )

    return resolved_ct, resolved_at, transient_rules



def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _to_float(value: Any) -> Optional[float]:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _serialize_parameter(param: ContractParameterExtracted) -> ParameterResponse:
    return ParameterResponse(
        parameter_id=param.parameter_id,
        contract_id=param.contract_id,
        header_name=param.header_name,
        param_name=param.param_name,
        original_extract=param.original_extract,
        user_override=param.user_override,
        match_score=_to_float(param.match_score),
        citation_text=param.citation_text,
        citation_start=param.citation_start,
        citation_end=param.citation_end,
        spatial_json=param.spatial_json,
        source_query=param.source_query,
        is_user_added=param.is_user_added,
        is_verified=param.is_verified,
        verification_note=param.verification_note,
        validation_state=param.validation_state,
        validation_message=param.validation_message,
        embed_model_name=param.embed_model_name,
        embed_dimension=param.embed_dimension,
        embed_quant_type=param.embed_quant_type,
        parser_version=param.parser_version,
        chunking_version=param.chunking_version,
        embed_created_at=param.embed_created_at,
        last_modified=param.last_modified,
    )


def _serialize_contract(contract: ContractMaster, include_document_text: bool = True) -> ContractResponse:
    return ContractResponse(
        contract_id=contract.contract_id,
        organization=contract.organization,
        business_unit=contract.business_unit,
        location=contract.location,
        department=contract.department,
        customer_partner_name=contract.customer_partner_name,
        financial_year=contract.financial_year,
        contract_type=contract.contract_type,
        agreement_type=contract.agreement_type,
        additional_info=contract.additional_info,
        contract_number=contract.contract_number,
        version_amendment_number=contract.version_amendment_number,
        execution_type=contract.execution_type,
        governing_entity=contract.governing_entity,
        jurisdiction=contract.jurisdiction,
        governing_law=contract.governing_law,
        legal_names_of_parties=contract.legal_names_of_parties,
        registered_addresses=contract.registered_addresses,
        cin_registration_numbers=contract.cin_registration_numbers,
        authorized_signatories=contract.authorized_signatories,
        contact_persons=contract.contact_persons,
        party_roles=contract.party_roles,
        affiliates_subsidiaries_involved=contract.affiliates_subsidiaries_involved,
        effective_date=contract.effective_date,
        uploaded_filename=contract.uploaded_filename,
        uploaded_content_type=contract.uploaded_content_type,
        workflow_state=contract.workflow_state,
        checked_out_by=contract.checked_out_by,
        checkout_expiry=contract.checkout_expiry,
        document_version=contract.document_version,
        created_by=contract.created_by,
        approved_by=contract.approved_by,
        risk_score=_to_float(contract.risk_score),
        risk_level=contract.risk_level,
        risk_rationale=contract.risk_rationale,
        draft_checkpoint=contract.draft_checkpoint,
        created_at=contract.created_at,
        updated_at=contract.updated_at,
        last_updated=contract.last_updated,
        document_text=contract.document_text if include_document_text else None,
        parameters=[_serialize_parameter(p) for p in contract.parameters],
    )


async def _load_contract(db: AsyncSession, contract_id: str) -> Optional[ContractMaster]:
    result = await db.execute(
        select(ContractMaster)
        .options(selectinload(ContractMaster.parameters))
        .where(ContractMaster.contract_id == contract_id)
        .execution_options(populate_existing=True)
    )
    return result.scalars().first()


def _write_audit(
    db: AsyncSession,
    contract_id: str,
    action_type: str,
    modified_by: str,
    field_changed: Optional[str] = None,
    old_value: Optional[str] = None,
    new_value: Optional[str] = None,
) -> None:
    db.add(ContractAuditTrail(
        contract_id=contract_id,
        action_type=action_type,
        field_changed=field_changed,
        old_value_clob=old_value,
        new_value_clob=new_value,
        modified_by=modified_by,
    ))


async def _upsert_metadata_option(db: AsyncSession, category: str, value: Optional[str]) -> None:
    if not value:
        return
    existing = await db.execute(
        select(MetadataOption).where(
            and_(MetadataOption.category == category, MetadataOption.value == value)
        )
    )
    if existing.scalars().first() is None:
        db.add(MetadataOption(category=category, value=value, is_active=True))


async def _load_active_rules(
    db: AsyncSession, contract_type: str, agreement_type: str
) -> List[MasterExtractionRule]:
    """
    Rule resolution order (most specific → least specific):
    1. UNIVERSAL rules always loaded (contract_type="UNIVERSAL")
    2. Exact match: contract_type + agreement_type  (specific rules)
    3. Fallback: contract_type only
    4. Fallback: agreement_type only (excluding UNIVERSAL to avoid dupes)
 
    Specific rules take precedence; UNIVERSAL rules fill remaining slots.
    This guarantees every upload gets the 10 core parameters extracted
    regardless of contract classification.
    """
    # Always load UNIVERSAL rules
    universal_q = await db.execute(
        select(MasterExtractionRule).where(
            and_(
                MasterExtractionRule.is_active == True,
                MasterExtractionRule.contract_type == "UNIVERSAL",
                MasterExtractionRule.agreement_type == "UNIVERSAL",
            )
        )
    )
    universal_rules = universal_q.scalars().all()
 
    # Try exact match
    exact = await db.execute(
        select(MasterExtractionRule).where(
            and_(
                MasterExtractionRule.is_active == True,
                MasterExtractionRule.contract_type == contract_type,
                MasterExtractionRule.agreement_type == agreement_type,
            )
        )
    )
    specific_rules = exact.scalars().all()
 
    if not specific_rules:
        # Fallback: contract_type only (exclude UNIVERSAL)
        ct_only = await db.execute(
            select(MasterExtractionRule).where(
                and_(
                    MasterExtractionRule.is_active == True,
                    MasterExtractionRule.contract_type == contract_type,
                    MasterExtractionRule.contract_type != "UNIVERSAL",
                )
            )
        )
        specific_rules = ct_only.scalars().all()
 
    if not specific_rules:
        # Fallback: agreement_type only (exclude UNIVERSAL to avoid duplicates)
        at_only = await db.execute(
            select(MasterExtractionRule).where(
                and_(
                    MasterExtractionRule.is_active == True,
                    MasterExtractionRule.agreement_type == agreement_type,
                    MasterExtractionRule.contract_type != "UNIVERSAL",
                )
            )
        )
        specific_rules = at_only.scalars().all()
 
    # Deduplicate: specific rules win over universal on same (head, name) key
    seen = {(r.parameter_head, r.parameter_name) for r in specific_rules}
    deduped_universal = [
        r for r in universal_rules
        if (r.parameter_head, r.parameter_name) not in seen
    ]
 
    return list(specific_rules) + deduped_universal



def _build_rule_payload(rule: MasterExtractionRule) -> Dict[str, Any]:
    return {
        "parameter_head": rule.parameter_head,
        "parameter_name": rule.parameter_name,
        "parameter_logic": rule.parameter_logic,
    }


# ── Upload ────────────────────────────────────────────────────────────────────

@router.post("/upload", response_model=ContractResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_contract(
    file: UploadFile = File(...),
    organization: str = Form(...),
    business_unit: str = Form(...),
    contract_type: str = Form(...),
    agreement_type: str = Form(...),
    user_id: str = Form(...),
    location: Optional[str] = Form(None),
    department: Optional[str] = Form(None),
    customer_partner_name: Optional[str] = Form(None),
    financial_year: Optional[str] = Form(None),
    additional_info: Optional[str] = Form(None),
    contract_number: Optional[str] = Form(None),
    version_amendment_number: Optional[str] = Form(None),
    execution_type: Optional[str] = Form(None),
    governing_entity: Optional[str] = Form(None),
    jurisdiction: Optional[str] = Form(None),
    governing_law: Optional[str] = Form(None),
    legal_names_of_parties: Optional[str] = Form(None),
    registered_addresses: Optional[str] = Form(None),
    cin_registration_numbers: Optional[str] = Form(None),
    authorized_signatories: Optional[str] = Form(None),
    contact_persons: Optional[str] = Form(None),
    party_roles: Optional[str] = Form(None),
    affiliates_subsidiaries_involved: Optional[str] = Form(None),
    effective_date: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    file_bytes = await file.read()
    content_type = file.content_type or ""

    contract_id = f"CON-{uuid.uuid4().hex[:10].upper()}"

    # ── Phase 1: UPLOADED state ──────────────────────────────────────────────
    contract = ContractMaster(
        contract_id=contract_id,
        organization=organization,
        business_unit=business_unit,
        location=location,
        department=department,
        customer_partner_name=customer_partner_name,
        financial_year=financial_year,
        contract_type=contract_type,
        agreement_type=agreement_type,
        additional_info=additional_info,
        contract_number=contract_number,
        version_amendment_number=version_amendment_number,
        execution_type=execution_type,
        governing_entity=governing_entity or business_unit,
        jurisdiction=jurisdiction,
        governing_law=governing_law,
        legal_names_of_parties=legal_names_of_parties,
        registered_addresses=registered_addresses,
        cin_registration_numbers=cin_registration_numbers,
        authorized_signatories=authorized_signatories,
        contact_persons=contact_persons,
        party_roles=party_roles,
        affiliates_subsidiaries_involved=affiliates_subsidiaries_involved,
        effective_date=_parse_date(effective_date),
        uploaded_filename=file.filename,
        uploaded_content_type=content_type,
        document_blob=file_bytes,
        document_text="",
        document_vector=None,
        workflow_state="UPLOADED",
        created_by=user_id,
    )
    db.add(contract)
    await db.flush()

    _write_audit(db, contract_id, "UPLOAD", user_id, "workflow_state", None, "UPLOADED")

    # ── Phase 2: PARSING state ───────────────────────────────────────────────
    contract.workflow_state = "PARSING"
    await db.flush()

    document_text, coord_index = extract_document_text(
        file.filename or "uploaded_document", content_type, file_bytes
    )
    if not document_text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not extract readable text from the uploaded document.",
        )

    contract.document_text = document_text
    await db.flush()

    # Build paragraph chunks + mean-pool document_vector
    mean_pool_vector = await _build_and_store_chunks(
        db=db,
        contract_id=contract_id,
        document_text=document_text,
        coord_index=coord_index,
    )
    contract.document_vector = emb.quantize_to_int8(mean_pool_vector)
    await db.flush()

    for cat, val in [
        ("organization", organization),
        ("business_unit", business_unit),
        ("location", location),
        ("department", department),
        ("customer_partner_name", customer_partner_name),
        ("financial_year", financial_year),
        ("contract_type", contract_type),
        ("agreement_type", agreement_type),
        ("execution_type", execution_type),
    ]:
        await _upsert_metadata_option(db, cat, val)

    await db.flush()

    # ── Phase 3: TAG_SUGGESTION_READY state ──────────────────────────────────
    suggestions = await tagging_agent.suggest_tags(document_text, file.filename)
    
    # Save suggestions
    db.add(ContractTagSuggestion(
        contract_id=contract_id,
        contract_type=suggestions["contract_type"]["value"],
        contract_type_confidence=suggestions["contract_type"]["confidence"],
        contract_type_rationale=suggestions["contract_type"]["rationale"],
        business_unit=suggestions["business_unit"]["value"],
        business_unit_confidence=suggestions["business_unit"]["confidence"],
        business_unit_rationale=suggestions["business_unit"]["rationale"],
        risk_level=suggestions["risk_level"]["value"],
        risk_level_confidence=suggestions["risk_level"]["confidence"],
        risk_level_rationale=suggestions["risk_level"]["rationale"],
        jurisdiction=suggestions["jurisdiction"]["value"],
        jurisdiction_confidence=suggestions["jurisdiction"]["confidence"],
        jurisdiction_rationale=suggestions["jurisdiction"]["rationale"],
        workflow_route=suggestions["workflow_route"]["value"],
        workflow_route_confidence=suggestions["workflow_route"]["confidence"],
        workflow_route_rationale=suggestions["workflow_route"]["rationale"],
        extraction_template=suggestions["extraction_template"]["value"],
        extraction_template_confidence=suggestions["extraction_template"]["confidence"],
        extraction_template_rationale=suggestions["extraction_template"]["rationale"],
    ))

    contract.workflow_state = "TAG_SUGGESTION_READY"
    _write_audit(
        db, contract_id, "TAG_SUGGESTIONS_GENERATED", "SYSTEM_AI",
        "workflow_state", "PARSING", "TAG_SUGGESTION_READY",
    )

    await db.commit()

    saved = await _load_contract(db, contract_id)
    if saved is None:
        raise HTTPException(status_code=500, detail="Contract persisted but could not be loaded.")
    return _serialize_contract(saved)


# ── Serve raw document (for PDF viewer) ───────────────────────────────────────


async def _execute_extraction_pipeline(db: AsyncSession, contract_id: str, user_id: str):
    """
    Executes the complete parameter extraction, deterministic validation, and risk assessment pipeline.
    Saves validation results and risk metrics directly on draft master and parameter tables.
    """
    contract = await db.get(ContractMaster, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    # ── Phase 1: EXTRACTION_RUNNING ──────────────────────────────────────────
    contract.workflow_state = "EXTRACTION_RUNNING"
    await db.flush()

    active_rules = await _load_active_rules(db, contract.contract_type, contract.agreement_type)
    rule_payloads = [_build_rule_payload(r) for r in active_rules]

    # If no rules exist, classify and inject dynamic rules
    if not active_rules:
        resolved_ct, resolved_at, rule_payloads = await _classify_and_inject_rules(
            document_text=contract.document_text,
            submitted_contract_type=contract.contract_type,
            submitted_agreement_type=contract.agreement_type,
            db=db,
            contract_id=contract_id,
        )
        contract.contract_type = resolved_ct
        contract.agreement_type = resolved_at
        await db.flush()

    # ── Phase 2: GROUNDING_RUNNING ───────────────────────────────────────────
    contract.workflow_state = "GROUNDING_RUNNING"
    await db.flush()

    extracted_params = await extraction_engine.run_extraction_for_rules(
        document_text=contract.document_text,
        rules=rule_payloads,
        file_bytes=contract.document_blob,
        content_type=contract.uploaded_content_type,
        coord_index=None,
        db=db,
        contract_id=contract_id,
    )

    # ── Phase 3: VALIDATION_RUNNING ──────────────────────────────────────────
    contract.workflow_state = "VALIDATION_RUNNING"
    await db.flush()

    # Clear existing extracted parameters if any
    existing_params = await db.execute(
        select(ContractParameterExtracted).where(ContractParameterExtracted.contract_id == contract_id)
    )
    for ep in existing_params.scalars().all():
        await db.delete(ep)
    await db.flush()

    # Map extracted params
    param_instances = []
    for item in extracted_params:
        p = ContractParameterExtracted(
            contract_id=contract_id,
            header_name=item["header_name"],
            param_name=item["param_name"],
            original_extract=item["original_extract"],
            user_override=item["user_override"],
            match_score=item["match_score"],
            citation_text=item["citation_text"],
            citation_start=item["citation_start"],
            citation_end=item["citation_end"],
            spatial_json=item["spatial_json"],
            vector_embed=emb.quantize_to_int8(item["vector_embed"]),
            source_query=item["source_query"],
            is_user_added=False,
            # Add embedding metadata!
            embed_model_name=settings.sentence_transformer_model,
            embed_dimension=settings.embedding_vector_dim,
            embed_quant_type="INT8",
            parser_version=settings.parser_version,
            chunking_version=settings.chunking_version,
        )
        db.add(p)
        param_instances.append(p)

    await db.flush()

    # Apply deterministic validation
    # Map model attributes to dictionaries for ValidationService
    param_dicts = []
    for p in param_instances:
        param_dicts.append({
            "param_name": p.param_name,
            "original_extract": p.original_extract,
            "user_override": p.user_override,
            "citation_text": p.citation_text,
            "_instance": p
        })

    validation_service.validate_contract_parameters(param_dicts)
    
    # Write back validation results
    for pd in param_dicts:
        p = pd["_instance"]
        p.validation_state = pd.get("validation_state", "needs_review")
        p.validation_message = pd.get("validation_message")

    # Run RiskAgent
    risk_params = []
    for p in param_instances:
        risk_params.append({
            "param_name": p.param_name,
            "original_extract": p.original_extract,
            "user_override": p.user_override,
        })
    score, level, rationale = await risk_agent.assess_risk(
        contract.contract_type, contract.agreement_type, risk_params
    )
    contract.risk_score = score
    contract.risk_level = level
    contract.risk_rationale = rationale

    # Check for manual review / fallback
    any_manual_review = any(
        p.validation_state in ("invalid", "needs_review", "missing_evidence")
        for p in param_instances
    )
    
    if any_manual_review:
        contract.workflow_state = "REVIEW_PENDING"
        _write_audit(
            db, contract_id, "MANUAL_REVIEW_REQUIRED", "SYSTEM_VALIDATION",
            "workflow_state", "VALIDATION_RUNNING", "REVIEW_PENDING"
        )
    else:
        contract.workflow_state = "DRAFT_READY"
        _write_audit(
            db, contract_id, "EXTRACTION_COMPLETE", "SYSTEM_EXTRACTION_ENGINE",
            "workflow_state", "VALIDATION_RUNNING", "DRAFT_READY"
        )

    await db.flush()


def _serialize_tag_suggestions(s: ContractTagSuggestion) -> ContractTagSuggestionResponse:
    return ContractTagSuggestionResponse(
        suggestion_id=s.suggestion_id,
        contract_id=s.contract_id,
        contract_type={"value": s.contract_type or "", "confidence": float(s.contract_type_confidence or 0.0), "rationale": s.contract_type_rationale or ""},
        business_unit={"value": s.business_unit or "", "confidence": float(s.business_unit_confidence or 0.0), "rationale": s.business_unit_rationale or ""},
        risk_level={"value": s.risk_level or "MEDIUM", "confidence": float(s.risk_level_confidence or 0.0), "rationale": s.risk_level_rationale or ""},
        jurisdiction={"value": s.jurisdiction or "", "confidence": float(s.jurisdiction_confidence or 0.0), "rationale": s.jurisdiction_rationale or ""},
        workflow_route={"value": s.workflow_route or "", "confidence": float(s.workflow_route_confidence or 0.0), "rationale": s.workflow_route_rationale or ""},
        extraction_template={"value": s.extraction_template or "", "confidence": float(s.extraction_template_confidence or 0.0), "rationale": s.extraction_template_rationale or ""},
        created_at=s.created_at,
    )


@router.get("/{contract_id}/suggest-tags", response_model=ContractTagSuggestionResponse)
async def get_suggested_tags(contract_id: str, db: AsyncSession = Depends(get_db)):
    """
    Returns suggested contract tags, confidence metrics, and rationale.
    If none exist (uploaded previously), runs TaggingAgent on-the-fly.
    """
    contract = await db.get(ContractMaster, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    result = await db.execute(
        select(ContractTagSuggestion).where(ContractTagSuggestion.contract_id == contract_id)
    )
    s = result.scalars().first()
    if s is not None:
        return _serialize_tag_suggestions(s)

    # Fallback suggestion generation
    suggestions = await tagging_agent.suggest_tags(contract.document_text or "", contract.uploaded_filename)
    s = ContractTagSuggestion(
        contract_id=contract_id,
        contract_type=suggestions["contract_type"]["value"],
        contract_type_confidence=suggestions["contract_type"]["confidence"],
        contract_type_rationale=suggestions["contract_type"]["rationale"],
        business_unit=suggestions["business_unit"]["value"],
        business_unit_confidence=suggestions["business_unit"]["confidence"],
        business_unit_rationale=suggestions["business_unit"]["rationale"],
        risk_level=suggestions["risk_level"]["value"],
        risk_level_confidence=suggestions["risk_level"]["confidence"],
        risk_level_rationale=suggestions["risk_level"]["rationale"],
        jurisdiction=suggestions["jurisdiction"]["value"],
        jurisdiction_confidence=suggestions["jurisdiction"]["confidence"],
        jurisdiction_rationale=suggestions["jurisdiction"]["rationale"],
        workflow_route=suggestions["workflow_route"]["value"],
        workflow_route_confidence=suggestions["workflow_route"]["confidence"],
        workflow_route_rationale=suggestions["workflow_route"]["rationale"],
        extraction_template=suggestions["extraction_template"]["value"],
        extraction_template_confidence=suggestions["extraction_template"]["confidence"],
        extraction_template_rationale=suggestions["extraction_template"]["rationale"],
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return _serialize_tag_suggestions(s)


@router.post("/{contract_id}/accept-tags", response_model=ContractResponse)
async def accept_tags(contract_id: str, payload: TagSuggestionsAcceptRequest, db: AsyncSession = Depends(get_db)):
    """
    Accepts suggested upload-time tags and triggers the extraction/grounding/validation pipeline.
    """
    contract = await db.get(ContractMaster, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    result = await db.execute(
        select(ContractTagSuggestion).where(ContractTagSuggestion.contract_id == contract_id)
    )
    s = result.scalars().first()
    if s is None:
        raise HTTPException(status_code=400, detail="No tag suggestions exist for this contract to accept.")

    prev_state = contract.workflow_state
    contract.contract_type = s.contract_type
    contract.business_unit = s.business_unit
    contract.jurisdiction = s.jurisdiction

    _write_audit(
        db, contract_id, "TAG_SUGGESTIONS_ACCEPTED", payload.modified_by,
        "contract_type/business_unit", f"{contract.contract_type}/{contract.business_unit}"
    )

    await _execute_extraction_pipeline(db, contract_id, payload.modified_by)
    await db.commit()

    saved = await _load_contract(db, contract_id)
    return _serialize_contract(saved)


@router.post("/{contract_id}/edit-tags", response_model=ContractResponse)
async def edit_tags(contract_id: str, payload: TagSuggestionsEditRequest, db: AsyncSession = Depends(get_db)):
    """
    Accepts user-edited tags and triggers the extraction/grounding/validation pipeline.
    """
    contract = await db.get(ContractMaster, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    prev_state = contract.workflow_state
    if payload.contract_type:
        contract.contract_type = payload.contract_type
    if payload.business_unit:
        contract.business_unit = payload.business_unit
    if payload.jurisdiction:
        contract.jurisdiction = payload.jurisdiction

    _write_audit(
        db, contract_id, "TAG_SUGGESTIONS_EDITED", payload.modified_by,
        "contract_type/business_unit", f"{contract.contract_type}/{contract.business_unit}"
    )

    await _execute_extraction_pipeline(db, contract_id, payload.modified_by)
    await db.commit()

    saved = await _load_contract(db, contract_id)
    return _serialize_contract(saved)


@router.post("/{contract_id}/pause", response_model=DraftPauseResponse)
async def pause_draft_review(contract_id: str, payload: DraftPauseRequest, db: AsyncSession = Depends(get_db)):
    """
    Persists mid-review draft review state to Oracle database and marks status as PAUSED.
    """
    contract = await db.get(ContractMaster, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    prev = contract.workflow_state
    contract.workflow_state = "PAUSED"
    contract.draft_checkpoint = payload.checkpoint_json

    _write_audit(
        db, contract_id, "DRAFT_PAUSED", payload.modified_by,
        "workflow_state", prev, "PAUSED"
    )
    await db.commit()

    return DraftPauseResponse(
        contract_id=contract_id,
        workflow_state="PAUSED",
        draft_checkpoint=contract.draft_checkpoint
    )


@router.post("/{contract_id}/resume", response_model=DraftPauseResponse)
async def resume_draft_review(contract_id: str, db: AsyncSession = Depends(get_db)):
    """
    Restores the contract review from PAUSED state back to USER_EDITING and fetches stored review state.
    """
    contract = await db.get(ContractMaster, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    prev = contract.workflow_state
    contract.workflow_state = "USER_EDITING"

    _write_audit(
        db, contract_id, "DRAFT_RESUMED", contract.checked_out_by or "SYSTEM",
        "workflow_state", prev, "USER_EDITING"
    )
    await db.commit()

    return DraftPauseResponse(
        contract_id=contract_id,
        workflow_state="USER_EDITING",
        draft_checkpoint=contract.draft_checkpoint
    )


@router.get("/{contract_id}/document")
async def get_contract_document(contract_id: str, db: AsyncSession = Depends(get_db)):
    """
    Returns the raw uploaded file bytes with the correct content-type.
    The frontend PDF viewer (PDF.js) fetches this endpoint and renders the file.
    """
    result = await db.execute(
        select(ContractMaster.document_blob, ContractMaster.uploaded_content_type, ContractMaster.uploaded_filename)
        .where(ContractMaster.contract_id == contract_id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Contract not found")

    blob, content_type, filename = row
    if not blob:
        raise HTTPException(status_code=404, detail="No document file stored for this contract")

    return Response(
        content=bytes(blob),
        media_type=content_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'inline; filename="{filename or contract_id}"',
            "Cache-Control": "private, max-age=3600",
        },
    )


# ── List / Search ─────────────────────────────────────────────────────────────

def _apply_filters(query, filters: Dict[str, Optional[str]]):
    mapping = {
        "organization": ContractMaster.organization,
        "business_unit": ContractMaster.business_unit,
        "location": ContractMaster.location,
        "department": ContractMaster.department,
        "contract_type": ContractMaster.contract_type,
        "agreement_type": ContractMaster.agreement_type,
        "customer_partner_name": ContractMaster.customer_partner_name,
        "financial_year": ContractMaster.financial_year,
        "workflow_state": ContractMaster.workflow_state,
    }
    for key, value in filters.items():
        if value and key in mapping:
            query = query.where(mapping[key] == value)
    return query


@router.get("", response_model=ContractListResponse)
async def list_contracts(
    organization: Optional[str] = None,
    business_unit: Optional[str] = None,
    location: Optional[str] = None,
    department: Optional[str] = None,
    contract_type: Optional[str] = None,
    agreement_type: Optional[str] = None,
    customer_partner_name: Optional[str] = None,
    financial_year: Optional[str] = None,
    workflow_state: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    filters = {
        "organization": organization, "business_unit": business_unit,
        "location": location, "department": department,
        "contract_type": contract_type, "agreement_type": agreement_type,
        "customer_partner_name": customer_partner_name,
        "financial_year": financial_year, "workflow_state": workflow_state,
    }
    base = select(ContractMaster).options(selectinload(ContractMaster.parameters))
    filtered = _apply_filters(base, filters).order_by(ContractMaster.last_updated.desc()).limit(limit).offset(offset)
    count_q = _apply_filters(select(func.count()).select_from(ContractMaster), filters)
    total = (await db.execute(count_q)).scalar_one()
    result = await db.execute(filtered)
    contracts = result.scalars().unique().all()
    return ContractListResponse(data=[_serialize_contract(c, include_document_text=False) for c in contracts], total=total)


@router.get("/search", response_model=ContractSearchResponse)
async def search_contracts(
    q: Optional[str] = None,
    organization: Optional[str] = None,
    business_unit: Optional[str] = None,
    contract_type: Optional[str] = None,
    agreement_type: Optional[str] = None,
    workflow_state: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(ContractMaster).options(selectinload(ContractMaster.parameters))
    query = _apply_filters(query, {
        "organization": organization, "business_unit": business_unit,
        "contract_type": contract_type, "agreement_type": agreement_type,
        "workflow_state": workflow_state,
    })
    if q:
        query = query.where(or_(
            ContractMaster.contract_id.ilike(f"%{q}%"),
            ContractMaster.contract_number.ilike(f"%{q}%"),
            ContractMaster.customer_partner_name.ilike(f"%{q}%"),
            ContractMaster.document_text.ilike(f"%{q}%"),
        ))
    query = query.order_by(ContractMaster.last_updated.desc())
    result = await db.execute(query)
    contracts = result.scalars().unique().all()
    return ContractSearchResponse(data=[_serialize_contract(c, include_document_text=False) for c in contracts], total=len(contracts))


@router.post("/semantic-search", response_model=SemanticSearchResponse)
async def semantic_search_contracts(
    q: str = Query(..., min_length=1, max_length=500, description="Natural language search query"),
    top_k: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """
    Searches contracts by semantic similarity using Oracle 26ai VECTOR_DISTANCE.
    Returns contracts ranked by relevance to the natural language query.
    Falls back to an empty result (not an error) if embeddings are unavailable.
    """
    hits = await emb.vector_search_documents(db=db, query_text=q, top_k=top_k)
    results = [
        SemanticSearchResult(
            contract_id=hit["contract_id"],
            contract_type=hit.get("contract_type"),
            agreement_type=hit.get("agreement_type"),
            organization=hit.get("organization"),
            uploaded_filename=hit.get("uploaded_filename"),
            similarity_score=round(max(0.0, 1.0 - float(hit.get("distance") or 1.0)), 4),
        )
        for hit in hits
    ]
    return SemanticSearchResponse(data=results, total=len(results), query=q)



@router.get("/{contract_id}", response_model=ContractResponse)
async def get_contract_details(contract_id: str, db: AsyncSession = Depends(get_db)):
    contract = await _load_contract(db, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    return _serialize_contract(contract)


# ── Lock / Unlock ─────────────────────────────────────────────────────────────

@router.post("/{contract_id}/lock", response_model=LockResponse)
async def acquire_lock(contract_id: str, payload: LockAcquireRequest, db: AsyncSession = Depends(get_db)):
    contract = await _load_contract(db, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    now = datetime.now(timezone.utc)
    if (
        contract.checked_out_by
        and contract.checked_out_by != payload.user_id
        and contract.checkout_expiry
        and contract.checkout_expiry > now
    ):
        raise HTTPException(status_code=409, detail=f"Locked by {contract.checked_out_by}")
    contract.checked_out_by = payload.user_id
    contract.checkout_expiry = now + timedelta(minutes=settings.lock_lease_minutes)
    _write_audit(db, contract_id, "LOCK_ACQUIRED", payload.user_id, "checked_out_by", None, payload.user_id)
    await db.commit()
    return LockResponse(contract_id=contract_id, checked_out_by=contract.checked_out_by, checkout_expiry=contract.checkout_expiry, lock_acquired=True)


@router.post("/{contract_id}/unlock")
async def release_lock(contract_id: str, payload: LockAcquireRequest, db: AsyncSession = Depends(get_db)):
    contract = await _load_contract(db, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    if contract.checked_out_by and contract.checked_out_by != payload.user_id:
        raise HTTPException(status_code=403, detail="Only lock owner can release lock")
    old_owner = contract.checked_out_by
    contract.checked_out_by = None
    contract.checkout_expiry = None
    _write_audit(db, contract_id, "LOCK_RELEASED", payload.user_id, "checked_out_by", old_owner, None)
    await db.commit()
    return {"status": "unlocked"}


# ── Parameter update / verify ─────────────────────────────────────────────────

@router.put("/{contract_id}/parameters/{param_id}", response_model=ParameterResponse)
async def update_parameter_override(
    contract_id: str, param_id: int, payload: ParameterUpdateRequest, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(ContractParameterExtracted).where(
            and_(ContractParameterExtracted.contract_id == contract_id, ContractParameterExtracted.parameter_id == param_id)
        )
    )
    param = result.scalars().first()
    if param is None:
        raise HTTPException(status_code=404, detail="Parameter not found")
    old = param.user_override
    param.user_override = payload.user_override
    param.last_modified = datetime.utcnow()
    contract = await db.get(ContractMaster, contract_id)
    if contract:
        contract.document_version = (contract.document_version or 1) + 1
    _write_audit(db, contract_id, "HUMAN_EDIT", payload.modified_by, f"parameter:{param_id}", old, payload.user_override)
    await db.commit()
    await db.refresh(param)
    return _serialize_parameter(param)


@router.post("/{contract_id}/parameters/{param_id}/verify", response_model=ParameterResponse)
async def verify_parameter(
    contract_id: str, param_id: int, payload: ParameterVerifyRequest, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(ContractParameterExtracted).where(
            and_(ContractParameterExtracted.contract_id == contract_id, ContractParameterExtracted.parameter_id == param_id)
        )
    )
    param = result.scalars().first()
    if param is None:
        raise HTTPException(status_code=404, detail="Parameter not found")
    param.is_verified = payload.is_verified
    param.verification_note = payload.note
    param.last_modified = datetime.utcnow()
    _write_audit(db, contract_id, "VERIFY_PARAMETER", payload.modified_by, f"parameter:{param_id}:verified", str(not payload.is_verified), str(payload.is_verified))
    await db.commit()
    await db.refresh(param)
    return _serialize_parameter(param)


@router.post("/{contract_id}/search-add", response_model=ParameterResponse, status_code=status.HTTP_201_CREATED)
async def add_parameter_from_search(
    contract_id: str, payload: DynamicSearchAddRequest, db: AsyncSession = Depends(get_db)
):
    contract = await _load_contract(db, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="Contract not found")

    extracted = await extraction_engine.run_extraction_for_rules(
        document_text=contract.document_text or "",
        rules=[{"parameter_head": payload.parameter_head, "parameter_name": payload.parameter_name, "parameter_logic": payload.query}],
        file_bytes=contract.document_blob,
        content_type=contract.uploaded_content_type,
        coord_index=None,          # Not available from stored state; spatial uses chunk DB.
        db=db,
        contract_id=contract_id,
    )
    item = extracted[0]
    if not item.get("original_extract"):
        raise HTTPException(status_code=422, detail="No matching text found in the document.")

    param = ContractParameterExtracted(
        contract_id=contract_id,
        header_name=item["header_name"],
        param_name=item["param_name"],
        original_extract=item["original_extract"],
        user_override=item["user_override"],
        match_score=item["match_score"],
        citation_text=item["citation_text"],
        citation_start=item["citation_start"],
        citation_end=item["citation_end"],
        spatial_json=item["spatial_json"],
        vector_embed=item["vector_embed"],
        source_query=payload.query,
        is_user_added=True,
    )
    db.add(param)
    _write_audit(db, contract_id, "USER_SEARCH_ADD", payload.modified_by, f"search_add:{payload.parameter_name}", None, payload.query)
    await db.commit()
    await db.refresh(param)
    return _serialize_parameter(param)


# ── Workflow transitions ───────────────────────────────────────────────────────

async def _transition(db, contract_id, state, payload, action_type):
    contract = await db.get(ContractMaster, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    prev = contract.workflow_state
    contract.workflow_state = state
    note = f"{state} | {payload.comment}" if payload.comment else state
    _write_audit(db, contract_id, action_type, payload.modified_by, "workflow_state", prev, note)
    await db.commit()
    return {"status": state}


@router.post("/{contract_id}/submit-draft")
async def submit_draft(contract_id: str, payload: WorkflowActionRequest, db: AsyncSession = Depends(get_db)):
    return await _transition(db, contract_id, "STAGED_DRAFT", payload, "SUBMIT_DRAFT")

@router.post("/{contract_id}/submit-approval")
async def submit_for_approval(contract_id: str, payload: WorkflowActionRequest, db: AsyncSession = Depends(get_db)):
    return await _transition(db, contract_id, "PENDING_APPROVAL", payload, "SUBMIT_FOR_APPROVAL")

@router.post("/{contract_id}/approve")
async def approve_contract(contract_id: str, payload: WorkflowActionRequest, db: AsyncSession = Depends(get_db)):
    """
    Transitions the contract to APPROVED state and atomically promotes it to the
    published tables via PublishingService.promote().

    The state change and the promotion are committed in the same transaction.
    If promotion fails, we log a warning but do NOT block the approval \u2014 the
    PublishingService is idempotent and can be retried. The contract will still be
    marked APPROVED in the draft table.
    """
    contract = await db.get(ContractMaster, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="Contract not found")

    prev = contract.workflow_state
    contract.workflow_state = "APPROVED"
    contract.approved_by = payload.modified_by
    note = f"APPROVED | {payload.comment}" if payload.comment else "APPROVED"
    _write_audit(db, contract_id, "APPROVE_CONTRACT", payload.modified_by, "workflow_state", prev, note)

    # Promote to published tables before committing so both changes are atomic.
    try:
        await publishing_service.promote(
            db=db,
            contract_id=contract_id,
            approved_by=payload.modified_by,
        )
    except Exception as exc:
        clm_logger.warning(
            f"[Approve] PublishingService.promote() failed for contract '{contract_id}': {exc}. "
            "Approval state change will still be committed. Promotion is idempotent and can be retried.",
            exc_info=True,
        )

    await db.commit()
    return {"status": "APPROVED"}

@router.post("/{contract_id}/send-back")
async def send_back_contract(contract_id: str, payload: WorkflowActionRequest, db: AsyncSession = Depends(get_db)):
    return await _transition(db, contract_id, "SENT_BACK", payload, "SEND_BACK")

@router.post("/{contract_id}/reject")
async def reject_contract(contract_id: str, payload: WorkflowActionRequest, db: AsyncSession = Depends(get_db)):
    return await _transition(db, contract_id, "SENT_BACK", payload, "REJECT_CONTRACT")


# ── Misc ───────────────────────────────────────────────────────────────────────

@router.get("/{contract_id}/compare")
async def compare_versions(contract_id: str, compare_to_id: str, db: AsyncSession = Depends(get_db)):
    first = await _load_contract(db, contract_id)
    second = await _load_contract(db, compare_to_id)
    if first is None or second is None:
        raise HTTPException(status_code=404, detail="One or both contracts not found")
    return {"contract1": _serialize_contract(first), "contract2": _serialize_contract(second)}


@router.post("/{contract_id}/clone", response_model=ContractResponse, status_code=status.HTTP_201_CREATED)
async def clone_contract_template(contract_id: str, payload: WorkflowActionRequest, db: AsyncSession = Depends(get_db)):
    source = await _load_contract(db, contract_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    clone_id = f"CON-{uuid.uuid4().hex[:10].upper()}"
    clone = ContractMaster(
        contract_id=clone_id, organization=source.organization, business_unit=source.business_unit,
        location=source.location, department=source.department, customer_partner_name=source.customer_partner_name,
        financial_year=source.financial_year, contract_type=source.contract_type, agreement_type=source.agreement_type,
        additional_info=source.additional_info, contract_number=source.contract_number,
        version_amendment_number=source.version_amendment_number, execution_type=source.execution_type,
        governing_entity=source.governing_entity, jurisdiction=source.jurisdiction, governing_law=source.governing_law,
        legal_names_of_parties=source.legal_names_of_parties, registered_addresses=source.registered_addresses,
        cin_registration_numbers=source.cin_registration_numbers, authorized_signatories=source.authorized_signatories,
        contact_persons=source.contact_persons, party_roles=source.party_roles,
        affiliates_subsidiaries_involved=source.affiliates_subsidiaries_involved,
        effective_date=source.effective_date, uploaded_filename=source.uploaded_filename,
        uploaded_content_type=source.uploaded_content_type, document_blob=source.document_blob,
        document_text=source.document_text, document_vector=source.document_vector,
        workflow_state="STAGED_DRAFT", created_by=payload.modified_by,
    )
    db.add(clone)
    await db.flush()
    for p in source.parameters:
        db.add(ContractParameterExtracted(
            contract_id=clone_id, header_name=p.header_name, param_name=p.param_name,
            original_extract=p.original_extract, user_override=p.user_override, match_score=p.match_score,
            citation_text=p.citation_text, citation_start=p.citation_start, citation_end=p.citation_end,
            spatial_json=p.spatial_json, vector_embed=p.vector_embed, source_query=p.source_query,
            is_user_added=p.is_user_added, is_verified=p.is_verified, verification_note=p.verification_note,
        ))
    _write_audit(db, clone_id, "CLONE_TEMPLATE", payload.modified_by, "template_source", contract_id, clone_id)
    await db.commit()
    cloned = await _load_contract(db, clone_id)
    return _serialize_contract(cloned)


@router.get("/{contract_id}/audit", response_model=AuditTrailResponse)
async def get_audit_trail(contract_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ContractAuditTrail)
        .where(ContractAuditTrail.contract_id == contract_id)
        .order_by(ContractAuditTrail.logged_timestamp.desc())
    )
    return AuditTrailResponse(contract_id=contract_id, audit_trail=result.scalars().all())


@router.get("/{contract_id}/parameters")
async def get_parameters(contract_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ContractParameterExtracted).where(ContractParameterExtracted.contract_id == contract_id)
    )
    return {"contract_id": contract_id, "parameters": [_serialize_parameter(p) for p in result.scalars().all()]}


@router.get("/{contract_id}/extraction-status", response_model=ExtractionStatusResponse)
async def get_extraction_status(contract_id: str, db: AsyncSession = Depends(get_db)):
    contract = await db.get(ContractMaster, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    result = await db.execute(
        select(ContractParameterExtracted).where(ContractParameterExtracted.contract_id == contract_id)
    )
    params = result.scalars().all()
    total = len(params)
    extracted = sum(1 for p in params if (p.original_extract or "").strip())
    verified = sum(1 for p in params if p.is_verified)
    return ExtractionStatusResponse(
        contract_id=contract_id, status=contract.workflow_state,
        total=total, extracted=extracted, verified=verified,
        percentage=int((verified / total) * 100) if total else 0,
    )


@router.post("/{contract_id}/re-extract", response_model=ReExtractionResponse)
async def re_extract_contract(
    contract_id: str,
    payload: WorkflowActionRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Re-runs LLM extraction for an already-uploaded contract.

    Use this after:
    - Fixing LLM provider configuration (e.g. swapping Cohere model)
    - Adding/modifying extraction rules for the contract's type
    - Any situation where the initial extraction produced empty fields

    All non-user-added parameters are deleted and replaced with fresh
    LLM output.  User-added parameters (is_user_added=True) are preserved.
    """
    contract = await _load_contract(db, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="Contract not found")

    if not contract.document_text:
        raise HTTPException(
            status_code=422,
            detail="Contract has no stored document text; re-upload the file.",
        )

    # Delete all LLM-generated parameters (preserve user-added ones)
    result = await db.execute(
        select(ContractParameterExtracted).where(
            ContractParameterExtracted.contract_id == contract_id,
            ContractParameterExtracted.is_user_added == False,  # noqa: E712
        )
    )
    stale_params = result.scalars().all()
    for p in stale_params:
        await db.delete(p)
    await db.flush()

    # Resolve rule set using the contract's stored classification
    active_rules = await _load_active_rules(
        db, contract.contract_type or "", contract.agreement_type or ""
    )

    if not active_rules:
        raise HTTPException(
            status_code=422,
            detail=(
                f"No active extraction rules found for contract_type=\"{contract.contract_type}\" "
                f"/ agreement_type=\"{contract.agreement_type}\". "
                "Add UNIVERSAL rules or create rules for this combination."
            ),
        )

    extracted_params = await extraction_engine.run_extraction_for_rules(
        document_text=contract.document_text,
        rules=[_build_rule_payload(r) for r in active_rules],
        file_bytes=contract.document_blob,
        content_type=contract.uploaded_content_type,
        coord_index=None,          # Not available from stored state; chunk vectors used for RAG.
        db=db,
        contract_id=contract_id,
    )

    parameters_filled = 0
    for item in extracted_params:
        if item.get("original_extract"):
            parameters_filled += 1
        db.add(ContractParameterExtracted(
            contract_id=contract_id,
            header_name=item["header_name"],
            param_name=item["param_name"],
            original_extract=item["original_extract"],
            user_override=item["user_override"],
            match_score=item["match_score"],
            citation_text=item["citation_text"],
            citation_start=item["citation_start"],
            citation_end=item["citation_end"],
            spatial_json=item["spatial_json"],
            vector_embed=item["vector_embed"],
            source_query=item["source_query"],
            is_user_added=False,
        ))

    _write_audit(
        db, contract_id, "RE_EXTRACT", payload.modified_by,
        "parameters", f"{len(stale_params)} stale rows deleted",
        f"{len(extracted_params)} rows written, {parameters_filled} filled",
    )
    await db.commit()

    return ReExtractionResponse(
        contract_id=contract_id,
        rules_applied=len(active_rules),
        parameters_written=len(extracted_params),
        parameters_filled=parameters_filled,
    )