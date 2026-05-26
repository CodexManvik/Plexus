from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.orm import ContractAuditTrail, ContractMaster
from app.schemas.pydantic_models import (
    ActivityLogItem,
    BacklogDepartmentItem,
    DashboardAnalyticsResponse,
    ExpiryContractItem,
    KPIDashboardResponse,
    KPIItem,
)

router = APIRouter(prefix="/dashboard", tags=["Executive Dashboard"])


def _fmt_date(value: date | None) -> str | None:
    return value.isoformat() if value else None


@router.get("", response_model=DashboardAnalyticsResponse)
async def get_dashboard_analytics(db: AsyncSession = Depends(get_db)):
    executed_query = select(func.count()).select_from(ContractMaster).where(
        ContractMaster.workflow_state == "APPROVED"
    )
    pending_query = select(func.count()).select_from(ContractMaster).where(
        ContractMaster.workflow_state.in_(["PENDING_APPROVAL", "STAGED_DRAFT", "SENT_BACK"])
    )

    today = date.today()
    horizon = today + timedelta(days=settings.dashboard_horizon_days)
    soon_query = select(func.count()).select_from(ContractMaster).where(
        ContractMaster.effective_date.is_not(None),
        ContractMaster.effective_date.between(today, horizon),
    )

    executed = (await db.execute(executed_query)).scalar_one()
    pending = (await db.execute(pending_query)).scalar_one()
    closing_soon = (await db.execute(soon_query)).scalar_one()

    kpis = KPIDashboardResponse(
        executed=KPIItem(value=executed, label="Approved contracts"),
        pending=KPIItem(value=pending, label="Draft + review backlog"),
        closingSoon=KPIItem(
            value=closing_soon,
            label=f"Effective in next {settings.dashboard_horizon_days} days",
            urgent=closing_soon > 0,
        ),
    )

    backlog_query = (
        select(ContractMaster.department, func.count())
        .where(ContractMaster.workflow_state.in_(["PENDING_APPROVAL", "STAGED_DRAFT", "SENT_BACK"]))
        .group_by(ContractMaster.department)
        .order_by(func.count().desc())
    )
    backlog_rows = (await db.execute(backlog_query)).all()
    backlog: List[BacklogDepartmentItem] = [
        BacklogDepartmentItem(department=row[0] or "Unassigned", count=row[1])
        for row in backlog_rows
    ]

    expiry_rows = (
        await db.execute(
            select(ContractMaster)
            .where(
                ContractMaster.effective_date.is_not(None),
                ContractMaster.effective_date.between(today, horizon),
            )
            .order_by(ContractMaster.effective_date.asc())
            .limit(20)
        )
    ).scalars().all()
    expiries = [
        ExpiryContractItem(
            contract_id=c.contract_id,
            title=f"{c.contract_type} - {c.agreement_type}",
            partner=c.customer_partner_name,
            daysLeft=max(0, (c.effective_date - today).days) if c.effective_date else 0,
            date=_fmt_date(c.effective_date),
            urgent=(c.effective_date - today).days <= 7 if c.effective_date else False,
        )
        for c in expiry_rows
    ]

    activity_rows = (
        await db.execute(
            select(ContractAuditTrail)
            .order_by(ContractAuditTrail.logged_timestamp.desc())
            .limit(30)
        )
    ).scalars().all()

    activity = [
        ActivityLogItem(
            title=f"{entry.contract_id} • {entry.action_type}",
            department=None,
            status=entry.action_type,
            owner=entry.modified_by,
            updated=entry.logged_timestamp.isoformat() if entry.logged_timestamp else None,
        )
        for entry in activity_rows
    ]

    return DashboardAnalyticsResponse(
        kpis=kpis,
        backlog=backlog,
        expiries=expiries,
        activity=activity,
    )


@router.get("/stats")
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)):
    total_query = select(func.count()).select_from(ContractMaster)
    approved_query = select(func.count()).select_from(ContractMaster).where(
        ContractMaster.workflow_state == "APPROVED"
    )
    pending_query = select(func.count()).select_from(ContractMaster).where(
        ContractMaster.workflow_state.in_(["PENDING_APPROVAL", "STAGED_DRAFT", "SENT_BACK"])
    )
    today = date.today()
    horizon = today + timedelta(days=settings.dashboard_horizon_days)
    expiring_query = select(func.count()).select_from(ContractMaster).where(
        ContractMaster.effective_date.is_not(None),
        ContractMaster.effective_date.between(today, horizon),
    )

    total = (await db.execute(total_query)).scalar_one()
    approved = (await db.execute(approved_query)).scalar_one()
    pending = (await db.execute(pending_query)).scalar_one()
    expiring = (await db.execute(expiring_query)).scalar_one()

    return {
        "totalContracts": total,
        "completedContracts": approved,
        "pendingApprovals": pending,
        "expiringContracts": expiring,
    }


@router.get("/recent")
async def get_recent_contracts(limit: int = 10, db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(ContractMaster)
            .order_by(ContractMaster.last_updated.desc())
            .limit(limit)
        )
    ).scalars().all()
    return {
        "data": [
            {
                "contract_id": c.contract_id,
                "organization": c.organization,
                "department": c.department,
                "type": c.contract_type,
                "agreementType": c.agreement_type,
                "status": c.workflow_state,
                "updated": c.last_updated.isoformat() if c.last_updated else None,
            }
            for c in rows
        ]
    }


@router.get("/pending-approvals")
async def get_pending_approvals(db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(ContractMaster)
            .where(ContractMaster.workflow_state == "PENDING_APPROVAL")
            .order_by(ContractMaster.last_updated.desc())
        )
    ).scalars().all()
    return {
        "data": [
            {
                "contract_id": c.contract_id,
                "organization": c.organization,
                "business_unit": c.business_unit,
                "department": c.department,
                "contract_type": c.contract_type,
                "agreement_type": c.agreement_type,
                "workflow_state": c.workflow_state,
                "checked_out_by": c.checked_out_by,
                "last_updated": c.last_updated.isoformat() if c.last_updated else None,
            }
            for c in rows
        ]
    }
