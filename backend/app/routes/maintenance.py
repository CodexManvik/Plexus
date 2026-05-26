from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_database_driver, get_db
from app.models.orm import ContractAuditTrail

router = APIRouter(prefix="/maintenance", tags=["Maintenance"])


@router.get("/status")
async def get_system_status(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        db_status = "operational"
    except Exception:
        db_status = "error"

    return {
        "status": "operational" if db_status == "operational" else "degraded",
        "database": db_status,
        "databaseDriver": get_database_driver(),
        "api": "operational",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/logs")
async def get_error_logs(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ContractAuditTrail)
        .order_by(ContractAuditTrail.logged_timestamp.desc())
        .limit(limit)
    )
    rows = result.scalars().all()
    return {
        "data": [
            {
                "id": row.audit_id,
                "contract_id": row.contract_id,
                "action_type": row.action_type,
                "modified_by": row.modified_by,
                "timestamp": row.logged_timestamp.isoformat()
                if row.logged_timestamp
                else None,
            }
            for row in rows
        ],
        "total": len(rows),
    }


@router.post("/sync", status_code=status.HTTP_200_OK)
async def trigger_sync():
    return {
        "status": "triggered",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": "Synchronization signal recorded.",
    }
