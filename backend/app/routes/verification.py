from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.orm import ContractAuditTrail, ContractParameterExtracted
from app.schemas.pydantic_models import ParameterResponse, ParameterVerifyRequest

router = APIRouter(prefix="/verification", tags=["Verification"])


def _serialize_parameter(parameter: ContractParameterExtracted) -> ParameterResponse:
    return ParameterResponse(
        parameter_id=parameter.parameter_id,
        contract_id=parameter.contract_id,
        header_name=parameter.header_name,
        param_name=parameter.param_name,
        original_extract=parameter.original_extract,
        user_override=parameter.user_override,
        match_score=float(parameter.match_score) if parameter.match_score is not None else None,
        citation_text=parameter.citation_text,
        citation_start=parameter.citation_start,
        citation_end=parameter.citation_end,
        spatial_json=parameter.spatial_json,
        source_query=parameter.source_query,
        is_user_added=parameter.is_user_added,
        is_verified=parameter.is_verified,
        verification_note=parameter.verification_note,
        last_modified=parameter.last_modified,
    )


@router.post("/{contract_id}/{param_id}/verify", response_model=ParameterResponse, status_code=status.HTTP_200_OK)
async def verify_parameter(
    contract_id: str,
    param_id: int,
    payload: ParameterVerifyRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ContractParameterExtracted).where(
            and_(
                ContractParameterExtracted.parameter_id == param_id,
                ContractParameterExtracted.contract_id == contract_id,
            )
        )
    )
    parameter = result.scalars().first()
    if parameter is None:
        raise HTTPException(status_code=404, detail="Parameter not found")

    parameter.is_verified = payload.is_verified
    parameter.verification_note = payload.note
    parameter.last_modified = datetime.utcnow()

    db.add(
        ContractAuditTrail(
            contract_id=contract_id,
            action_type="VERIFY_PARAMETER",
            field_changed=f"parameter:{param_id}:verified",
            old_value_clob=None,
            new_value_clob=str(payload.is_verified),
            modified_by=payload.modified_by,
        )
    )

    await db.commit()
    await db.refresh(parameter)
    return _serialize_parameter(parameter)
