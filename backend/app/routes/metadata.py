from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.orm import ContractMaster, MetadataOption
from app.schemas.pydantic_models import (
    MetadataBundleResponse,
    MetadataOptionCreate,
    MetadataOptionResponse,
)

router = APIRouter(prefix="/metadata", tags=["Metadata"])


async def _distinct_values(
    db: AsyncSession,
    category: str,
    contract_column=None,
) -> List[str]:
    values: List[str] = []
    option_rows = await db.execute(
        select(MetadataOption.value)
        .where(
            MetadataOption.category == category,
            MetadataOption.is_active.is_(True),
        )
        .order_by(MetadataOption.value.asc())
    )
    values.extend(option_rows.scalars().all())

    if contract_column is not None:
        contract_rows = await db.execute(
            select(distinct(contract_column)).where(contract_column.is_not(None))
        )
        values.extend(contract_rows.scalars().all())

    deduped = sorted({value.strip() for value in values if value and value.strip()})
    return deduped


@router.get("/options", response_model=List[MetadataOptionResponse])
async def list_metadata_options(
    category: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(MetadataOption).where(MetadataOption.is_active.is_(True))
    if category:
        query = query.where(MetadataOption.category == category)
    query = query.order_by(MetadataOption.category.asc(), MetadataOption.value.asc())

    result = await db.execute(query)
    return result.scalars().all()


@router.post("/options", response_model=MetadataOptionResponse, status_code=status.HTTP_201_CREATED)
async def create_metadata_option(
    payload: MetadataOptionCreate,
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(
        select(MetadataOption).where(
            MetadataOption.category == payload.category,
            MetadataOption.value == payload.value,
        )
    )
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="Metadata option already exists")

    row = MetadataOption(
        category=payload.category.strip(),
        value=payload.value.strip(),
        is_active=True,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.get("/bundle", response_model=MetadataBundleResponse)
async def get_metadata_bundle(db: AsyncSession = Depends(get_db)):
    return MetadataBundleResponse(
        organizations=await _distinct_values(db, "organization", ContractMaster.organization),
        business_units=await _distinct_values(db, "business_unit", ContractMaster.business_unit),
        locations=await _distinct_values(db, "location", ContractMaster.location),
        departments=await _distinct_values(db, "department", ContractMaster.department),
        customer_partner_names=await _distinct_values(
            db, "customer_partner_name", ContractMaster.customer_partner_name
        ),
        financial_years=await _distinct_values(db, "financial_year", ContractMaster.financial_year),
        contract_types=await _distinct_values(db, "contract_type", ContractMaster.contract_type),
        agreement_types=await _distinct_values(db, "agreement_type", ContractMaster.agreement_type),
        execution_types=await _distinct_values(db, "execution_type", ContractMaster.execution_type),
    )


@router.get("/organizations")
async def get_organizations(db: AsyncSession = Depends(get_db)):
    return {"data": await _distinct_values(db, "organization", ContractMaster.organization)}


@router.get("/business-units")
async def get_business_units(db: AsyncSession = Depends(get_db)):
    return {"data": await _distinct_values(db, "business_unit", ContractMaster.business_unit)}


@router.get("/locations")
async def get_locations(db: AsyncSession = Depends(get_db)):
    return {"data": await _distinct_values(db, "location", ContractMaster.location)}


@router.get("/departments")
async def get_departments(db: AsyncSession = Depends(get_db)):
    return {"data": await _distinct_values(db, "department", ContractMaster.department)}


@router.get("/customer-partners")
async def get_customer_partners(db: AsyncSession = Depends(get_db)):
    return {
        "data": await _distinct_values(
            db, "customer_partner_name", ContractMaster.customer_partner_name
        )
    }


@router.get("/financial-years")
async def get_financial_years(db: AsyncSession = Depends(get_db)):
    return {"data": await _distinct_values(db, "financial_year", ContractMaster.financial_year)}


@router.get("/contract-types")
async def get_contract_types(db: AsyncSession = Depends(get_db)):
    return {"data": await _distinct_values(db, "contract_type", ContractMaster.contract_type)}


@router.get("/agreement-types")
async def get_agreement_types(db: AsyncSession = Depends(get_db)):
    return {"data": await _distinct_values(db, "agreement_type", ContractMaster.agreement_type)}


@router.get("/execution-types")
async def get_execution_types(db: AsyncSession = Depends(get_db)):
    return {"data": await _distinct_values(db, "execution_type", ContractMaster.execution_type)}
