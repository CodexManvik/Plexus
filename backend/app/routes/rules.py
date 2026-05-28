from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.orm import MasterExtractionRule
from app.schemas.pydantic_models import (
    MasterRuleCreate,
    MasterRuleResponse,
    MasterRuleUpdate,
)

router = APIRouter(prefix="/rules", tags=["Master Rules Config"])


@router.get("", response_model=list[MasterRuleResponse])
async def list_active_rules(
    contract_type: str | None = None,
    agreement_type: str | None = None,
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
):
    query = select(MasterExtractionRule)
    if not include_inactive:
        query = query.where(MasterExtractionRule.is_active == True)
    if contract_type:
        query = query.where(MasterExtractionRule.contract_type == contract_type)
    if agreement_type:
        query = query.where(MasterExtractionRule.agreement_type == agreement_type)
    query = query.order_by(
        MasterExtractionRule.contract_type.asc(),
        MasterExtractionRule.agreement_type.asc(),
        MasterExtractionRule.parameter_head.asc(),
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/pending", response_model=list[MasterRuleResponse])
async def list_pending_rules(
    contract_type: str | None = None,
    agreement_type: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Returns AI-proposed rules staged for admin review (is_active=False, created_by='SYSTEM_AI_PROPOSAL')."""
    query = select(MasterExtractionRule).where(
        MasterExtractionRule.is_active == False,
        MasterExtractionRule.created_by == "SYSTEM_AI_PROPOSAL",
    )
    if contract_type:
        query = query.where(MasterExtractionRule.contract_type == contract_type)
    if agreement_type:
        query = query.where(MasterExtractionRule.agreement_type == agreement_type)
    query = query.order_by(MasterExtractionRule.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/{rule_id}/activate", response_model=MasterRuleResponse)
async def activate_pending_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Activates an AI-proposed rule, making it available for future extractions."""
    row = await db.get(MasterExtractionRule, rule_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    if row.is_active:
        raise HTTPException(status_code=400, detail="Rule is already active")
    row.is_active = True
    await db.commit()
    await db.refresh(row)
    return row


@router.post("", response_model=MasterRuleResponse, status_code=status.HTTP_201_CREATED)
async def define_parameter_logic_rule(
    payload: MasterRuleCreate,
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(
        select(MasterExtractionRule).where(
            and_(
                MasterExtractionRule.contract_type == payload.contract_type,
                MasterExtractionRule.agreement_type == payload.agreement_type,
                MasterExtractionRule.parameter_head == payload.parameter_head,
                MasterExtractionRule.parameter_name == payload.parameter_name,
            )
        )
    )
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="Rule already exists")

    row = MasterExtractionRule(
        contract_type=payload.contract_type,
        agreement_type=payload.agreement_type,
        parameter_head=payload.parameter_head,
        parameter_name=payload.parameter_name,
        parameter_logic=payload.parameter_logic,
        is_active=payload.is_active,
        created_by=payload.created_by,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.put("/{rule_id}", response_model=MasterRuleResponse)
async def update_parameter_logic_rule(
    rule_id: int,
    payload: MasterRuleUpdate,
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(MasterExtractionRule, rule_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Rule not found")

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(row, key, value)

    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/{rule_id}")
async def delete_parameter_rule(rule_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(MasterExtractionRule, rule_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    await db.delete(row)
    await db.commit()
    return {"message": "Rule removed successfully.", "rule_id": rule_id}
