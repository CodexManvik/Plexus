"""
assistant.py — RAG chatbot using Oracle 23ai VECTOR_DISTANCE for retrieval.

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

from app.database import get_db
from app.models.orm import ContractMaster
from app.schemas.pydantic_models import (
    AssistantQueryRequest,
    AssistantQueryResponse,
    AssistantSourceSnippet,
)
from app.services import embeddings as emb
from app.services.llm import azure_llm

router = APIRouter(prefix="/assistant", tags=["Assistant"])

# ── Keyword fallback (used when vector embeddings unavailable) ────────────────

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


# ── Main query endpoint ────────────────────────────────────────────────────────

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
    # ── 1. Resolve which contracts to search ────────────────────────────────
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

    # ── 2. Vector retrieval (Oracle 23ai VECTOR_DISTANCE) ───────────────────
    vector_hits = await emb.vector_search_parameters(
        db,
        query_text=payload.question,
        contract_ids=resolved_ids if contract_ids else None,
        top_k=payload.top_k * 2,  # over-fetch then re-rank
    )

    sources: List[AssistantSourceSnippet] = []

    # Convert vector hits to source snippets (cosine distance → score 0-1)
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

    # ── 3. Keyword fallback if vector search returned nothing ────────────────
    if not sources:
        q_tokens = _tokenize(payload.question)
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

        # Also search raw document text
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

    # ── 4. Build prompt and call Azure OpenAI ───────────────────────────────
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

    answer = await azure_llm.get_chat_completion(system_prompt, user_prompt)
    used_llm = bool(answer.strip())

    if not used_llm:
        lines = [
            "Azure OpenAI is not configured — retrieval-only summary.",
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