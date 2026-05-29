"""
publishing.py \u2014 PublishingService for promoting approved contracts to the published trust zone.

Design:
  - promote() is the single entry point. It does NOT commit \u2014 the caller (approve endpoint)
    owns the transaction so the approval state change and the promotion are atomic.
  - Idempotency: if a PublishedContract row already exists for a given contract_id, the
    existing published_id is returned and no duplicate rows are written.
  - effective_value resolution: user_override takes precedence over original_extract.
    This materialises the final human-approved value at promotion time, so the published
    table is self-contained and does not require joins back to the draft table.
  - Embeddings are copied as-is from the draft rows \u2014 they are identical content so there
    is no need to re-compute them.
  - ContractDocumentChunks are also promoted so that the assistant can perform
    published-only vector search at the chunk level.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.orm import (
    ContractAuditTrail,
    ContractDocumentChunk,
    ContractMaster,
    ContractParameterExtracted,
    PublishedChunk,
    PublishedContract,
    PublishedParameter,
)
from app.services.logger import clm_logger


class PublishingService:
    """
    Promotes an approved contract from the draft tables to the published trust zone.

    Usage
    -----
    service = PublishingService()
    published = await service.promote(db, contract_id, approved_by)
    # do NOT commit here \u2014 caller commits together with the approval state change
    """

    async def promote(
        self,
        db: AsyncSession,
        contract_id: str,
        approved_by: str,
    ) -> PublishedContract:
        """
        Promotes a contract to the published tables.

        Steps:
          1. Check for an existing publication (idempotent \u2014 returns existing if found).
          2. Load ContractMaster with its parameters and chunks.
          3. Insert a PublishedContract row.
          4. Copy each ContractParameterExtracted to PublishedParameter
             (user_override wins over original_extract as effective_value).
          5. Copy each ContractDocumentChunk to PublishedChunk.
          6. Write a ContractAuditTrail entry with action_type='PUBLISHED'.

        Does NOT commit — caller owns the transaction.

        Backward-compatible wrapper for promote_draft_to_published.
        """
        return await self.promote_draft_to_published(db, contract_id, approved_by)

    async def promote_draft_to_published(
        self,
        db: AsyncSession,
        contract_id: str,
        approved_by: str,
    ) -> PublishedContract:
        """
        Atomically promotes an approved contract staging workspace (draft) to the published trust zone,
        and wipes clean the transient staging schemas upon successful promotion.
        """
        # ── Idempotency check ──────────────────────────────────────────────────
        existing_publication = await db.execute(
            select(PublishedContract).where(PublishedContract.contract_id == contract_id)
        )
        existing = existing_publication.scalars().first()
        if existing is not None:
            clm_logger.info(
                f"[Publishing] Contract '{contract_id}' already published "
                f"(published_id={existing.published_id}). Returning existing record."
            )
            return existing

        # ── Load draft master with its relations ──────────────────────────────
        result = await db.execute(
            select(ContractMaster)
            .options(
                selectinload(ContractMaster.parameters),
            )
            .where(ContractMaster.contract_id == contract_id)
        )
        contract = result.scalars().first()
        if contract is None:
            raise ValueError(f"Contract '{contract_id}' not found — cannot promote to published.")

        # Load chunks separately (ContractMaster may not have a relationship to chunks defined)
        chunk_result = await db.execute(
            select(ContractDocumentChunk)
            .where(ContractDocumentChunk.contract_id == contract_id)
            .order_by(ContractDocumentChunk.chunk_index)
        )
        chunks = chunk_result.scalars().all()

        now_utc = datetime.now(timezone.utc)

        # ────────────────────────────────────────────────────────────────────────
        published_contract = PublishedContract(
            contract_id=contract_id,
            contract_type=contract.contract_type,
            agreement_type=contract.agreement_type,
            organization=contract.organization,
            business_unit=contract.business_unit,
            customer_partner_name=contract.customer_partner_name,
            effective_date=contract.effective_date,
            approved_by=approved_by,
            approved_at=now_utc,
            risk_score=contract.risk_score,
            risk_level=contract.risk_level,
            risk_rationale=contract.risk_rationale,
            published_at=now_utc,
        )
        db.add(published_contract)
        # Flush to obtain published_id before writing children.
        await db.flush()

        clm_logger.info(
            f"[Publishing] Created PublishedContract published_id={published_contract.published_id} "
            f"for contract '{contract_id}'."
        )

        # ────────────────────────────────────────────────────────────────────────
        parameter_count = 0
        for param in contract.parameters:
            # Resolve effective_value: human edit (user_override) wins over machine extract.
            effective_value: Optional[str] = (
                param.user_override.strip() if param.user_override and param.user_override.strip()
                else (param.original_extract or None)
            )
            db.add(PublishedParameter(
                published_id=published_contract.published_id,
                contract_id=contract_id,
                header_name=param.header_name,
                param_name=param.param_name,
                effective_value=effective_value,
                citation_text=param.citation_text,
                citation_start=param.citation_start,
                citation_end=param.citation_end,
                spatial_json=param.spatial_json,
                vector_embed=param.vector_embed,
                source_query=param.source_query,
                validation_state=param.validation_state,
                validation_message=param.validation_message,
                embed_model_name=param.embed_model_name,
                embed_dimension=param.embed_dimension,
                embed_quant_type="INT8",
                parser_version=param.parser_version,
                chunking_version=param.chunking_version,
                embed_created_at=param.embed_created_at,
            ))
            parameter_count += 1

        # ────────────────────────────────────────────────────────────────────────
        chunk_count = 0
        for chunk in chunks:
            db.add(PublishedChunk(
                published_id=published_contract.published_id,
                contract_id=contract_id,
                chunk_index=chunk.chunk_index,
                chunk_text=chunk.chunk_text,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                spatial_json=chunk.spatial_json,
                chunk_vector=chunk.chunk_vector,
                embed_model_name=chunk.embed_model_name,
                embed_dimension=chunk.embed_dimension,
                embed_quant_type="INT8",
                parser_version=chunk.parser_version,
                chunking_version=chunk.chunking_version,
                embed_created_at=chunk.embed_created_at,
            ))
            chunk_count += 1

        # ────────────────────────────────────────────────────────────────────────
        db.add(ContractAuditTrail(
            contract_id=contract_id,
            action_type="PUBLISHED",
            field_changed="published_contracts",
            old_value_clob=None,
            new_value_clob=json.dumps({
                "published_id": published_contract.published_id,
                "approved_by": approved_by,
                "parameter_count": parameter_count,
                "chunk_count": chunk_count,
            }),
            modified_by=approved_by,
        ))

        clm_logger.info(
            f"[Publishing] Promoted contract '{contract_id}' — "
            f"{parameter_count} parameters, {chunk_count} chunks — "
            f"approved_by='{approved_by}'."
        )

        # ── Wipe Clean Transient Workspace Draft Schemas ──────────────────────
        clm_logger.info(f"[Publishing] Wiping draft staging records from database workspace for '{contract_id}'...")
        await db.delete(contract)

        return published_contract


# Module-level singleton \u2014 stateless service, safe to share across requests.
publishing_service = PublishingService()
