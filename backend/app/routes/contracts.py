from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models.orm import (
    ContractAuditTrail,
    ContractMaster,
    ContractParameterExtracted,
    MasterExtractionRule,
    MetadataOption,
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
    WorkflowActionRequest,
)
from app.services.document_parser import extract_document_text
from app.services.ocr import extraction_engine

router = APIRouter(prefix="/contracts", tags=["Contracts Workflow"])


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
        created_at=contract.created_at,
        updated_at=contract.updated_at,
        last_updated=contract.last_updated,
        document_text=contract.document_text if include_document_text else None,
        parameters=[_serialize_parameter(param) for param in contract.parameters],
    )


async def _load_contract(db: AsyncSession, contract_id: str) -> Optional[ContractMaster]:
    result = await db.execute(
        select(ContractMaster)
        .options(selectinload(ContractMaster.parameters))
        .where(ContractMaster.contract_id == contract_id)
    )
    return result.scalars().first()


async def _write_audit(
    db: AsyncSession,
    contract_id: str,
    action_type: str,
    modified_by: str,
    field_changed: Optional[str] = None,
    old_value: Optional[str] = None,
    new_value: Optional[str] = None,
) -> None:
    db.add(
        ContractAuditTrail(
            contract_id=contract_id,
            action_type=action_type,
            field_changed=field_changed,
            old_value_clob=old_value,
            new_value_clob=new_value,
            modified_by=modified_by,
        )
    )


async def _upsert_metadata_option(db: AsyncSession, category: str, value: Optional[str]) -> None:
    if not value:
        return
    existing = await db.execute(
        select(MetadataOption).where(
            and_(
                MetadataOption.category == category,
                MetadataOption.value == value,
            )
        )
    )
    if existing.scalars().first() is None:
        db.add(MetadataOption(category=category, value=value, is_active=True))


async def _load_active_rules(
    db: AsyncSession, contract_type: str, agreement_type: str
) -> List[MasterExtractionRule]:
    exact = await db.execute(
        select(MasterExtractionRule).where(
            and_(
                MasterExtractionRule.is_active == True,
                MasterExtractionRule.contract_type == contract_type,
                MasterExtractionRule.agreement_type == agreement_type,
            )
        )
    )
    exact_rules = exact.scalars().all()
    if exact_rules:
        return exact_rules

    fallback = await db.execute(
        select(MasterExtractionRule).where(
            and_(
                MasterExtractionRule.is_active == True,
                MasterExtractionRule.contract_type == contract_type,
            )
        )
    )
    return fallback.scalars().all()


def _build_rule_payload(rule: MasterExtractionRule) -> Dict[str, Any]:
    return {
        "parameter_head": rule.parameter_head,
        "parameter_name": rule.parameter_name,
        "parameter_logic": rule.parameter_logic,
    }


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
    document_text = extract_document_text(file.filename or "uploaded_document", file.content_type, file_bytes)

    if not document_text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not extract readable text from the uploaded document.",
        )

    contract_id = f"CON-{uuid.uuid4().hex[:10].upper()}"
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
        uploaded_content_type=file.content_type,
        document_text=document_text,
        workflow_state="STAGED_DRAFT",
        created_by=user_id,
    )
    db.add(contract)

    await _upsert_metadata_option(db, "organization", organization)
    await _upsert_metadata_option(db, "business_unit", business_unit)
    await _upsert_metadata_option(db, "location", location)
    await _upsert_metadata_option(db, "department", department)
    await _upsert_metadata_option(db, "customer_partner_name", customer_partner_name)
    await _upsert_metadata_option(db, "financial_year", financial_year)
    await _upsert_metadata_option(db, "contract_type", contract_type)
    await _upsert_metadata_option(db, "agreement_type", agreement_type)
    await _upsert_metadata_option(db, "execution_type", execution_type)

    await db.flush()

    active_rules = await _load_active_rules(db, contract_type, agreement_type)
    if active_rules:
        extracted_params = await extraction_engine.run_extraction_for_rules(
            document_text=document_text,
            rules=[_build_rule_payload(rule) for rule in active_rules],
        )
        for item in extracted_params:
            db.add(
                ContractParameterExtracted(
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
                )
            )

    await _write_audit(
        db,
        contract_id=contract_id,
        action_type="UPLOAD",
        modified_by=user_id,
        field_changed="workflow_state",
        old_value=None,
        new_value="STAGED_DRAFT",
    )
    await db.commit()

    saved = await _load_contract(db, contract_id)
    if saved is None:
        raise HTTPException(status_code=500, detail="Contract persisted but could not be loaded.")
    return _serialize_contract(saved)


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
        "organization": organization,
        "business_unit": business_unit,
        "location": location,
        "department": department,
        "contract_type": contract_type,
        "agreement_type": agreement_type,
        "customer_partner_name": customer_partner_name,
        "financial_year": financial_year,
        "workflow_state": workflow_state,
    }

    base_query = select(ContractMaster).options(selectinload(ContractMaster.parameters))
    filtered_query = _apply_filters(base_query, filters)
    filtered_query = filtered_query.order_by(ContractMaster.last_updated.desc()).limit(limit).offset(offset)

    count_query = _apply_filters(select(func.count()).select_from(ContractMaster), filters)
    total = (await db.execute(count_query)).scalar_one()

    result = await db.execute(filtered_query)
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
    query = _apply_filters(
        query,
        {
            "organization": organization,
            "business_unit": business_unit,
            "contract_type": contract_type,
            "agreement_type": agreement_type,
            "workflow_state": workflow_state,
        },
    )

    if q:
        query = query.where(
            or_(
                ContractMaster.contract_id.ilike(f"%{q}%"),
                ContractMaster.contract_number.ilike(f"%{q}%"),
                ContractMaster.customer_partner_name.ilike(f"%{q}%"),
                ContractMaster.document_text.ilike(f"%{q}%"),
                ContractMaster.additional_info.ilike(f"%{q}%"),
            )
        )

    query = query.order_by(ContractMaster.last_updated.desc())
    result = await db.execute(query)
    contracts = result.scalars().unique().all()
    return ContractSearchResponse(
        data=[_serialize_contract(c, include_document_text=False) for c in contracts],
        total=len(contracts),
    )


@router.get("/{contract_id}", response_model=ContractResponse)
async def get_contract_details(contract_id: str, db: AsyncSession = Depends(get_db)):
    contract = await _load_contract(db, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    return _serialize_contract(contract)


@router.post("/{contract_id}/lock", response_model=LockResponse)
async def acquire_lock(
    contract_id: str,
    payload: LockAcquireRequest,
    db: AsyncSession = Depends(get_db),
):
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
        raise HTTPException(
            status_code=409,
            detail=f"Contract is currently locked by {contract.checked_out_by}",
        )

    contract.checked_out_by = payload.user_id
    contract.checkout_expiry = now + timedelta(minutes=settings.lock_lease_minutes)
    await _write_audit(
        db,
        contract_id=contract_id,
        action_type="LOCK_ACQUIRED",
        modified_by=payload.user_id,
        field_changed="checked_out_by",
        old_value=None,
        new_value=payload.user_id,
    )
    await db.commit()
    return LockResponse(
        contract_id=contract_id,
        checked_out_by=contract.checked_out_by,
        checkout_expiry=contract.checkout_expiry,
        lock_acquired=True,
    )


@router.post("/{contract_id}/unlock")
async def release_lock(
    contract_id: str,
    payload: LockAcquireRequest,
    db: AsyncSession = Depends(get_db),
):
    contract = await _load_contract(db, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="Contract not found")

    if contract.checked_out_by and contract.checked_out_by != payload.user_id:
        raise HTTPException(status_code=403, detail="Only lock owner can release lock")

    old_owner = contract.checked_out_by
    contract.checked_out_by = None
    contract.checkout_expiry = None
    await _write_audit(
        db,
        contract_id=contract_id,
        action_type="LOCK_RELEASED",
        modified_by=payload.user_id,
        field_changed="checked_out_by",
        old_value=old_owner,
        new_value=None,
    )
    await db.commit()
    return {"status": "unlocked"}


@router.put("/{contract_id}/parameters/{param_id}", response_model=ParameterResponse)
async def update_parameter_override(
    contract_id: str,
    param_id: int,
    payload: ParameterUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ContractParameterExtracted).where(
            and_(
                ContractParameterExtracted.contract_id == contract_id,
                ContractParameterExtracted.parameter_id == param_id,
            )
        )
    )
    parameter = result.scalars().first()
    if parameter is None:
        raise HTTPException(status_code=404, detail="Parameter not found")

    old_value = parameter.user_override
    parameter.user_override = payload.user_override
    parameter.last_modified = datetime.utcnow()

    contract = await db.get(ContractMaster, contract_id)
    if contract:
        contract.document_version = (contract.document_version or 1) + 1

    await _write_audit(
        db,
        contract_id=contract_id,
        action_type="HUMAN_EDIT",
        modified_by=payload.modified_by,
        field_changed=f"parameter:{param_id}",
        old_value=old_value,
        new_value=payload.user_override,
    )
    await db.commit()
    await db.refresh(parameter)
    return _serialize_parameter(parameter)


@router.post("/{contract_id}/parameters/{param_id}/verify", response_model=ParameterResponse)
async def verify_parameter(
    contract_id: str,
    param_id: int,
    payload: ParameterVerifyRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ContractParameterExtracted).where(
            and_(
                ContractParameterExtracted.contract_id == contract_id,
                ContractParameterExtracted.parameter_id == param_id,
            )
        )
    )
    parameter = result.scalars().first()
    if parameter is None:
        raise HTTPException(status_code=404, detail="Parameter not found")

    parameter.is_verified = payload.is_verified
    parameter.verification_note = payload.note
    parameter.last_modified = datetime.utcnow()

    await _write_audit(
        db,
        contract_id=contract_id,
        action_type="VERIFY_PARAMETER",
        modified_by=payload.modified_by,
        field_changed=f"parameter:{param_id}:verified",
        old_value=str(not payload.is_verified),
        new_value=str(payload.is_verified),
    )
    await db.commit()
    await db.refresh(parameter)
    return _serialize_parameter(parameter)


@router.post("/{contract_id}/search-add", response_model=ParameterResponse, status_code=status.HTTP_201_CREATED)
async def add_parameter_from_search(
    contract_id: str,
    payload: DynamicSearchAddRequest,
    db: AsyncSession = Depends(get_db),
):
    contract = await _load_contract(db, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="Contract not found")

    extracted = await extraction_engine.run_extraction_for_rules(
        document_text=contract.document_text or "",
        rules=[
            {
                "parameter_head": payload.parameter_head,
                "parameter_name": payload.parameter_name,
                "parameter_logic": payload.query,
            }
        ],
    )
    item = extracted[0]
    parameter = ContractParameterExtracted(
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
        source_query=payload.query,
        is_user_added=True,
    )
    db.add(parameter)

    await _write_audit(
        db,
        contract_id=contract_id,
        action_type="USER_SEARCH_ADD",
        modified_by=payload.modified_by,
        field_changed=f"search_add:{payload.parameter_name}",
        old_value=None,
        new_value=payload.query,
    )
    await db.commit()
    await db.refresh(parameter)
    return _serialize_parameter(parameter)


async def _transition_workflow(
    db: AsyncSession,
    contract_id: str,
    workflow_state: str,
    payload: WorkflowActionRequest,
    action_type: str,
) -> Dict[str, str]:
    contract = await db.get(ContractMaster, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="Contract not found")

    previous_state = contract.workflow_state
    contract.workflow_state = workflow_state
    if workflow_state == "APPROVED":
        contract.approved_by = payload.modified_by

    await _write_audit(
        db,
        contract_id=contract_id,
        action_type=action_type,
        modified_by=payload.modified_by,
        field_changed="workflow_state",
        old_value=previous_state,
        new_value=workflow_state if not payload.comment else f"{workflow_state} | {payload.comment}",
    )
    await db.commit()
    return {"status": workflow_state}


@router.post("/{contract_id}/submit-draft")
async def submit_draft(
    contract_id: str,
    payload: WorkflowActionRequest,
    db: AsyncSession = Depends(get_db),
):
    return await _transition_workflow(
        db,
        contract_id=contract_id,
        workflow_state="STAGED_DRAFT",
        payload=payload,
        action_type="SUBMIT_DRAFT",
    )


@router.post("/{contract_id}/submit-approval")
async def submit_for_approval(
    contract_id: str,
    payload: WorkflowActionRequest,
    db: AsyncSession = Depends(get_db),
):
    return await _transition_workflow(
        db,
        contract_id=contract_id,
        workflow_state="PENDING_APPROVAL",
        payload=payload,
        action_type="SUBMIT_FOR_APPROVAL",
    )


@router.post("/{contract_id}/approve")
async def approve_contract(
    contract_id: str,
    payload: WorkflowActionRequest,
    db: AsyncSession = Depends(get_db),
):
    return await _transition_workflow(
        db,
        contract_id=contract_id,
        workflow_state="APPROVED",
        payload=payload,
        action_type="APPROVE_CONTRACT",
    )


@router.post("/{contract_id}/send-back")
async def send_back_contract(
    contract_id: str,
    payload: WorkflowActionRequest,
    db: AsyncSession = Depends(get_db),
):
    return await _transition_workflow(
        db,
        contract_id=contract_id,
        workflow_state="SENT_BACK",
        payload=payload,
        action_type="SEND_BACK",
    )


@router.post("/{contract_id}/reject")
async def reject_contract(
    contract_id: str,
    payload: WorkflowActionRequest,
    db: AsyncSession = Depends(get_db),
):
    return await _transition_workflow(
        db,
        contract_id=contract_id,
        workflow_state="SENT_BACK",
        payload=payload,
        action_type="REJECT_CONTRACT",
    )


@router.get("/{contract_id}/compare")
async def compare_versions(
    contract_id: str,
    compare_to_id: str,
    db: AsyncSession = Depends(get_db),
):
    first = await _load_contract(db, contract_id)
    second = await _load_contract(db, compare_to_id)
    if first is None or second is None:
        raise HTTPException(status_code=404, detail="One or both contracts not found")

    return {
        "contract1": _serialize_contract(first),
        "contract2": _serialize_contract(second),
    }


@router.post("/{contract_id}/clone", response_model=ContractResponse, status_code=status.HTTP_201_CREATED)
async def clone_contract_template(
    contract_id: str,
    payload: WorkflowActionRequest,
    db: AsyncSession = Depends(get_db),
):
    source = await _load_contract(db, contract_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Contract not found")

    clone_id = f"CON-{uuid.uuid4().hex[:10].upper()}"
    clone = ContractMaster(
        contract_id=clone_id,
        organization=source.organization,
        business_unit=source.business_unit,
        location=source.location,
        department=source.department,
        customer_partner_name=source.customer_partner_name,
        financial_year=source.financial_year,
        contract_type=source.contract_type,
        agreement_type=source.agreement_type,
        additional_info=source.additional_info,
        contract_number=source.contract_number,
        version_amendment_number=source.version_amendment_number,
        execution_type=source.execution_type,
        governing_entity=source.governing_entity,
        jurisdiction=source.jurisdiction,
        governing_law=source.governing_law,
        legal_names_of_parties=source.legal_names_of_parties,
        registered_addresses=source.registered_addresses,
        cin_registration_numbers=source.cin_registration_numbers,
        authorized_signatories=source.authorized_signatories,
        contact_persons=source.contact_persons,
        party_roles=source.party_roles,
        affiliates_subsidiaries_involved=source.affiliates_subsidiaries_involved,
        effective_date=source.effective_date,
        uploaded_filename=source.uploaded_filename,
        uploaded_content_type=source.uploaded_content_type,
        document_text=source.document_text,
        workflow_state="STAGED_DRAFT",
        created_by=payload.modified_by,
    )
    db.add(clone)
    await db.flush()

    for param in source.parameters:
        db.add(
            ContractParameterExtracted(
                contract_id=clone_id,
                header_name=param.header_name,
                param_name=param.param_name,
                original_extract=param.original_extract,
                user_override=param.user_override,
                match_score=param.match_score,
                citation_text=param.citation_text,
                citation_start=param.citation_start,
                citation_end=param.citation_end,
                spatial_json=param.spatial_json,
                source_query=param.source_query,
                is_user_added=param.is_user_added,
                is_verified=param.is_verified,
                verification_note=param.verification_note,
            )
        )

    await _write_audit(
        db,
        contract_id=clone_id,
        action_type="CLONE_TEMPLATE",
        modified_by=payload.modified_by,
        field_changed="template_source",
        old_value=contract_id,
        new_value=clone_id,
    )
    await db.commit()
    cloned = await _load_contract(db, clone_id)
    if cloned is None:
        raise HTTPException(status_code=500, detail="Cloned contract could not be loaded")
    return _serialize_contract(cloned)


@router.get("/{contract_id}/audit", response_model=AuditTrailResponse)
async def get_audit_trail(contract_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ContractAuditTrail)
        .where(ContractAuditTrail.contract_id == contract_id)
        .order_by(ContractAuditTrail.logged_timestamp.desc())
    )
    audits = result.scalars().all()
    return AuditTrailResponse(contract_id=contract_id, audit_trail=audits)


@router.get("/{contract_id}/parameters")
async def get_parameters(contract_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ContractParameterExtracted).where(
            ContractParameterExtracted.contract_id == contract_id
        )
    )
    params = result.scalars().all()
    return {"contract_id": contract_id, "parameters": [_serialize_parameter(p) for p in params]}


@router.get("/{contract_id}/extraction-status", response_model=ExtractionStatusResponse)
async def get_extraction_status(contract_id: str, db: AsyncSession = Depends(get_db)):
    contract = await db.get(ContractMaster, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="Contract not found")

    result = await db.execute(
        select(ContractParameterExtracted).where(
            ContractParameterExtracted.contract_id == contract_id
        )
    )
    params = result.scalars().all()
    total = len(params)
    extracted = sum(1 for p in params if (p.original_extract or "").strip())
    verified = sum(1 for p in params if p.is_verified)
    percentage = int((verified / total) * 100) if total else 0

    return ExtractionStatusResponse(
        contract_id=contract_id,
        status=contract.workflow_state,
        total=total,
        extracted=extracted,
        verified=verified,
        percentage=percentage,
    )
