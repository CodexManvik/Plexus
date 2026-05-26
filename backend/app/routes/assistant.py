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
from app.services.llm import azure_llm

router = APIRouter(prefix="/assistant", tags=["Assistant"])

TOKEN_RE = re.compile(r"[A-Za-z0-9']+")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "have",
    "will",
    "shall",
    "must",
    "into",
    "your",
    "their",
    "have",
    "been",
    "are",
    "was",
    "were",
    "not",
    "any",
    "all",
    "can",
    "may",
    "our",
    "you",
    "we",
    "but",
    "or",
    "its",
    "within",
    "under",
    "over",
    "than",
    "then",
    "there",
    "here",
    "each",
    "such",
}


def _tokenize(text: str) -> List[str]:
    return [token.lower() for token in TOKEN_RE.findall(text or "") if len(token) > 2 and token.lower() not in STOPWORDS]


def _score(query_tokens: List[str], candidate: str) -> float:
    if not query_tokens or not candidate:
        return 0.0

    candidate_tokens = _tokenize(candidate)
    if not candidate_tokens:
        return 0.0

    query_counts = Counter(query_tokens)
    candidate_counts = Counter(candidate_tokens)
    overlap = sum(min(query_counts[token], candidate_counts[token]) for token in query_counts)
    if overlap <= 0:
        return 0.0

    coverage = overlap / max(len(query_tokens), 1)
    density = overlap / max(len(candidate_tokens), 1)
    return round((coverage * 0.7) + (density * 0.3), 4)


def _split_sentences(text: str) -> List[str]:
    return [sentence.strip() for sentence in SENTENCE_SPLIT_RE.split(text or "") if sentence.strip()]


def _best_sentence(text: str, query_tokens: List[str]) -> tuple[str, float]:
    best_sentence = ""
    best_score = 0.0
    for sentence in _split_sentences(text):
        score = _score(query_tokens, sentence)
        if score > best_score:
            best_sentence = sentence
            best_score = score
    if best_sentence:
        return best_sentence, best_score
    fallback = (text or "").strip().replace("\n", " ")
    return fallback[:500], _score(query_tokens, fallback[:500]) if fallback else 0.0


async def _load_contracts(db: AsyncSession, contract_ids: List[str]) -> List[ContractMaster]:
    query = (
        select(ContractMaster)
        .options(selectinload(ContractMaster.parameters))
        .where(ContractMaster.contract_id.in_(contract_ids))
    )
    result = await db.execute(query)
    contracts = result.scalars().all()
    if not contracts:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No matching documents found.")

    order_index = {contract_id: index for index, contract_id in enumerate(contract_ids)}
    contracts.sort(key=lambda contract: order_index.get(contract.contract_id, len(order_index)))
    return contracts


@router.post("/query", response_model=AssistantQueryResponse)
async def ask_assistant(payload: AssistantQueryRequest, db: AsyncSession = Depends(get_db)):
    contract_ids = [contract_id for contract_id in payload.contract_ids if contract_id.strip()]
    if not contract_ids:
        recent = await db.execute(
            select(ContractMaster)
            .options(selectinload(ContractMaster.parameters))
            .order_by(ContractMaster.updated_at.desc().nullslast(), ContractMaster.created_at.desc().nullslast())
            .limit(5)
        )
        contracts = recent.scalars().all()
        if not contracts:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No documents available for retrieval.")
    else:
        contracts = await _load_contracts(db, contract_ids)

    query_tokens = _tokenize(payload.question)
    candidate_sources: List[AssistantSourceSnippet] = []

    for contract in contracts:
        document_text = contract.document_text or ""
        document_sentence, document_score = _best_sentence(document_text, query_tokens)
        summary_bits = [
            contract.uploaded_filename or contract.contract_id,
            contract.contract_type,
            contract.agreement_type,
            contract.organization,
            contract.business_unit,
            contract.department,
            contract.workflow_state,
        ]
        summary_text = " | ".join(bit for bit in summary_bits if bit)
        summary_score = _score(query_tokens, summary_text + " " + document_sentence)
        if document_sentence:
            candidate_sources.append(
                AssistantSourceSnippet(
                    contract_id=contract.contract_id,
                    contract_type=contract.contract_type,
                    agreement_type=contract.agreement_type,
                    source_type="document",
                    title=contract.uploaded_filename or contract.contract_id,
                    snippet=document_sentence[:700],
                    score=summary_score or document_score,
                )
            )

        for parameter in contract.parameters:
            parameter_text = " ".join(
                value
                for value in [
                    parameter.header_name,
                    parameter.param_name,
                    parameter.user_override,
                    parameter.original_extract,
                    parameter.citation_text,
                    parameter.source_query,
                ]
                if value
            )
            score = _score(query_tokens, parameter_text)
            if score <= 0:
                continue

            snippet = parameter.user_override or parameter.original_extract or parameter.citation_text or parameter_text
            candidate_sources.append(
                AssistantSourceSnippet(
                    contract_id=contract.contract_id,
                    contract_type=contract.contract_type,
                    agreement_type=contract.agreement_type,
                    source_type="parameter",
                    title=f"{parameter.header_name} / {parameter.param_name}",
                    snippet=snippet[:700],
                    score=score,
                    parameter_head=parameter.header_name,
                    parameter_name=parameter.param_name,
                )
            )

    candidate_sources.sort(key=lambda item: item.score, reverse=True)
    selected_sources = candidate_sources[: max(payload.top_k, 1)]
    if not selected_sources:
        selected_sources = [
            AssistantSourceSnippet(
                contract_id=contract.contract_id,
                contract_type=contract.contract_type,
                agreement_type=contract.agreement_type,
                source_type="document",
                title=contract.uploaded_filename or contract.contract_id,
                snippet=(contract.document_text or "")[:700],
                score=0.0,
            )
            for contract in contracts[: payload.top_k]
        ]

    source_context = []
    for index, source in enumerate(selected_sources, start=1):
        source_context.append(
            f"{index}. [{source.contract_id}] {source.title} ({source.source_type}, score={source.score:.2f})\n{source.snippet}"
        )

    system_prompt = (
        "You are ContractLens AI, a contract retrieval assistant. "
        "Answer strictly from the provided contract excerpts. "
        "If the excerpts do not contain the answer, say that the selected documents do not show it. "
        "Be concise, practical, and cite the relevant contract IDs when possible."
    )
    user_prompt = (
        f"Question: {payload.question}\n\n"
        f"Selected documents: {', '.join(contract.contract_id for contract in contracts)}\n\n"
        "Relevant excerpts:\n"
        + "\n\n".join(source_context)
    )

    answer = await azure_llm.get_chat_completion(system_prompt, user_prompt)
    used_llm = bool(answer.strip())
    if not used_llm:
        answer_lines = [
            "Azure OpenAI is not configured, so this is a retrieval-only summary.",
            "",
            f"Question: {payload.question}",
        ]
        for source in selected_sources:
            answer_lines.append(
                f"- [{source.contract_id}] {source.title}: {source.snippet}"
            )
        answer = "\n".join(answer_lines)

    return AssistantQueryResponse(
        answer=answer,
        contract_ids=[contract.contract_id for contract in contracts],
        sources=selected_sources,
        used_llm=used_llm,
    )