"""
assistant.py \u2014 RAG chatbot using Oracle 26ai VECTOR_DISTANCE for retrieval.

Default mode (draft_mode=False):
  Retrieval targets published_parameters and published_chunks \u2014 only approved data
  surfaces to the assistant. This is the production-safe path.

Draft mode (draft_mode=True):
  Retrieval falls back to contract_parameters_extracted (draft tables). Intended
  for development and debugging. A warning is emitted when used in non-development
  environments.

Falls back to keyword scoring if embeddings are unavailable.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models.orm import ContractMaster
from app.schemas.pydantic_models import (
    AssistantQueryRequest,
    AssistantQueryResponse,
    AssistantSourceSnippet,
)
from app.services import embeddings as emb
from app.services.llm import cohere_llm
from app.services.logger import clm_logger

router = APIRouter(prefix="/assistant", tags=["Assistant"])

# \u2500\u2500 Keyword fallback (used when vector embeddings unavailable) ────────────────

TOKEN_RE = re.compile(r"[A-Za-z0-9']+")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "have", "will",
    "shall", "must", "into", "your", "their", "been", "are", "was", "were",
    "not", "any", "all", "can", "may", "our", "you", "we", "but", "or",
    "its", "within", "under", "over", "than", "then", "there", "here",
    "each", "such",
}


def _tokenize(text: str) -> List[str]:
    return [
        t.lower() for t in TOKEN_RE.findall(text or "")
        if len(t) > 2 and t.lower() not in STOPWORDS
    ]


def _score(query_tokens: List[str], candidate: str) -> float:
    if not query_tokens or not candidate:
        return 0.0
    c_tokens = _tokenize(candidate)
    if not c_tokens:
        return 0.0
    qc = Counter(query_tokens)
    cc = Counter(c_tokens)
    overlap = sum(min(qc[t], cc[t]) for t in qc)
    if overlap <= 0:
        return 0.0
    return round((overlap / max(len(query_tokens), 1)) * 0.7 + (overlap / max(len(c_tokens), 1)) * 0.3, 4)


def _best_sentence(text: str, q_tokens: List[str]) -> tuple[str, float]:
    best_s, best_sc = "", 0.0
    for s in SENTENCE_SPLIT_RE.split(text or ""):
        s = s.strip()
        sc = _score(q_tokens, s)
        if sc > best_sc:
            best_s, best_sc = s, sc
    if best_s:
        return best_s, best_sc
    fallback = (text or "").strip().replace("\n", " ")[:500]
    return fallback, _score(q_tokens, fallback)


# \u2500\u2500 Main query endpoint ────────────────────────────────────────────────────────

async def _load_contracts(db: AsyncSession, contract_ids: List[str]) -> List[ContractMaster]:
    q = (
        select(ContractMaster)
        .options(selectinload(ContractMaster.parameters))
        .where(ContractMaster.contract_id.in_(contract_ids))
    )
    result = await db.execute(q)
    contracts = result.scalars().all()
    if not contracts:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No matching documents found.")
    order = {cid: i for i, cid in enumerate(contract_ids)}
    contracts.sort(key=lambda c: order.get(c.contract_id, len(order)))
    return contracts


@router.post("/query", response_model=AssistantQueryResponse)
async def ask_assistant(payload: AssistantQueryRequest, db: AsyncSession = Depends(get_db)):
    # \u2500\u2500 draft_mode guard: warn when used outside development \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    if payload.draft_mode and getattr(settings, "app_env", "production") != "development":
        clm_logger.warning(
            "[Assistant] draft_mode=True requested in a non-development environment. "
            "This exposes unapproved draft data to the assistant. "
            "Set APP_ENV=development in .env to suppress this warning."
        )

    # \u2500\u2500 1. Resolve which contracts to search \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    contract_ids = [cid for cid in payload.contract_ids if cid.strip()]
    if not contract_ids:
        recent = await db.execute(
            select(ContractMaster)
            .options(selectinload(ContractMaster.parameters))
            .order_by(ContractMaster.updated_at.desc().nullslast())
            .limit(5)
        )
        contracts = recent.scalars().all()
        if not contracts:
            raise HTTPException(status_code=404, detail="No documents available.")
    else:
        contracts = await _load_contracts(db, contract_ids)

    resolved_ids = [c.contract_id for c in contracts]

    # \u2500\u2500 2. Vector retrieval (Oracle 26ai VECTOR_DISTANCE) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    sources: List[AssistantSourceSnippet] = []

    if payload.draft_mode:
        # Draft path: query the unreviewed draft parameter table.
        vector_hits = await emb.vector_search_parameters(
            db,
            query_text=payload.question,
            contract_ids=resolved_ids if contract_ids else None,
            top_k=payload.top_k * 2,
        )
        for hit in vector_hits:
            distance = float(hit.get("distance") or 1.0)
            score = round(max(0.0, 1.0 - distance), 4)
            snippet = hit.get("user_override") or hit.get("original_extract") or hit.get("citation_text") or ""
            sources.append(
                AssistantSourceSnippet(
                    contract_id=hit["contract_id"],
                    contract_type=hit.get("contract_type"),
                    agreement_type=hit.get("agreement_type"),
                    source_type="parameter",
                    title=f"{hit.get('header_name', '')} / {hit.get('param_name', '')}",
                    snippet=snippet[:700],
                    score=score,
                    parameter_head=hit.get("header_name"),
                    parameter_name=hit.get("param_name"),
                )
            )
    else:
        # Published path (default): query only approved, promoted data.
        vector_hits = await emb.vector_search_published_parameters(
            db,
            query_text=payload.question,
            contract_ids=resolved_ids if contract_ids else None,
            top_k=payload.top_k * 2,
        )
        for hit in vector_hits:
            distance = float(hit.get("distance") or 1.0)
            score = round(max(0.0, 1.0 - distance), 4)
            # Published table uses effective_value instead of user_override/original_extract
            snippet = hit.get("effective_value") or hit.get("citation_text") or ""
            sources.append(
                AssistantSourceSnippet(
                    contract_id=hit["contract_id"],
                    contract_type=hit.get("contract_type"),
                    agreement_type=hit.get("agreement_type"),
                    source_type="parameter",
                    title=f"{hit.get('header_name', '')} / {hit.get('param_name', '')}",
                    snippet=snippet[:700],
                    score=score,
                    parameter_head=hit.get("header_name"),
                    parameter_name=hit.get("param_name"),
                )
            )

    # \u2500\u2500 3. Keyword fallback if vector search returned nothing \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    if not sources:
        q_tokens = _tokenize(payload.question)
        if payload.draft_mode:
            # Draft keyword fallback: iterate over ORM parameters loaded with contracts.
            for contract in contracts:
                for param in contract.parameters:
                    combined = " ".join(
                        v for v in [
                            param.header_name, param.param_name,
                            param.user_override, param.original_extract,
                            param.citation_text,
                        ]
                        if v
                    )
                    sc = _score(q_tokens, combined)
                    if sc <= 0:
                        continue
                    snippet = param.user_override or param.original_extract or param.citation_text or ""
                    sources.append(
                        AssistantSourceSnippet(
                            contract_id=contract.contract_id,
                            contract_type=contract.contract_type,
                            agreement_type=contract.agreement_type,
                            source_type="parameter",
                            title=f"{param.header_name} / {param.param_name}",
                            snippet=snippet[:700],
                            score=sc,
                            parameter_head=param.header_name,
                            parameter_name=param.param_name,
                        )
                    )
        else:
            # Published keyword fallback: iterate over ContractMaster document text only.
            # We do not expose draft ORM parameters in the published path.
            for contract in contracts:
                doc_sentence, doc_score = _best_sentence(contract.document_text or "", q_tokens)
                if doc_sentence and doc_score > 0:
                    sources.append(
                        AssistantSourceSnippet(
                            contract_id=contract.contract_id,
                            contract_type=contract.contract_type,
                            agreement_type=contract.agreement_type,
                            source_type="document",
                            title=contract.uploaded_filename or contract.contract_id,
                            snippet=doc_sentence[:700],
                            score=doc_score,
                        )
                    )

        if payload.draft_mode:
            # Also search raw document text in draft mode.
            for contract in contracts:
                doc_sentence, doc_score = _best_sentence(contract.document_text or "", q_tokens)
                if doc_sentence:
                    sources.append(
                        AssistantSourceSnippet(
                            contract_id=contract.contract_id,
                            contract_type=contract.contract_type,
                            agreement_type=contract.agreement_type,
                            source_type="document",
                            title=contract.uploaded_filename or contract.contract_id,
                            snippet=doc_sentence[:700],
                            score=doc_score,
                        )
                    )

        sources.sort(key=lambda s: s.score, reverse=True)

    selected = sources[: max(payload.top_k, 1)]

    # \u2500\u2500 4. Build prompt and call Cohere \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    context_lines = []
    for i, src in enumerate(selected, 1):
        context_lines.append(
            f"{i}. [{src.contract_id}] {src.title} (score={src.score:.2f})\n{src.snippet}"
        )

    system_prompt = (
        "You are a contract retrieval assistant. "
        "Answer strictly from the provided contract excerpts. "
        "If the excerpts do not contain the answer, say the selected documents do not show it. "
        "Be concise and cite relevant contract IDs."
    )
    user_prompt = (
        f"Question: {payload.question}\n\n"
        f"Selected contracts: {', '.join(resolved_ids)}\n\n"
        "Relevant excerpts:\n" + "\n\n".join(context_lines)
    )

    answer = await cohere_llm.get_chat_completion(system_prompt, user_prompt)
    used_llm = bool(answer.strip())

    if not used_llm:
        lines = [
            "Cohere is not configured \u2014 retrieval-only summary.",
            f"\nQuestion: {payload.question}",
        ]
        for src in selected:
            lines.append(f"- [{src.contract_id}] {src.title}: {src.snippet}")
        answer = "\n".join(lines)

    return AssistantQueryResponse(
        answer=answer,
        contract_ids=resolved_ids,
        sources=selected,
        used_llm=used_llm,
    )