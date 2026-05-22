import uuid

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db, init_db
from .embeddings import embed_texts
from .models import Contract, ContractParameter, ContractVersion
from .schemas import (
    ContractCreateRequest,
    ContractParameterResponse,
    ContractVersionResponse,
    ExtractionRequest,
    ParameterResponse,
    SearchRequest,
    SearchResult,
    UpdateParameterRequest,
)
from .services.extraction import run_extraction, update_user_override

settings = get_settings()
app = FastAPI(title="Plexus ICMS Local API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    if settings.init_db:
        init_db()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def _version_to_response(version: ContractVersion) -> ContractVersionResponse:
    return ContractVersionResponse(
        contract_id=version.contract_id,
        version_number=version.version_number,
        workflow_state=version.workflow_state,
        is_current=version.is_current,
        etag=version.etag,
    )


def _get_version(db: Session, contract_id: str, version_number: int) -> ContractVersion:
    stmt = select(ContractVersion).where(
        ContractVersion.contract_id == contract_id,
        ContractVersion.version_number == version_number,
    )
    version = db.execute(stmt).scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=404, detail="Contract version not found")
    return version


def _validate_etag(version: ContractVersion, if_match: str | None) -> None:
    if if_match and if_match != version.etag:
        raise HTTPException(status_code=409, detail="ETag mismatch")


def _next_version(db: Session, contract_id: str) -> int:
    stmt = select(func.max(ContractVersion.version_number)).where(
        ContractVersion.contract_id == contract_id
    )
    max_version = db.execute(stmt).scalar()
    return (max_version or 0) + 1


def _set_versions_not_current(db: Session, contract_id: str) -> None:
    stmt = (
        update(ContractVersion)
        .where(ContractVersion.contract_id == contract_id)
        .values(is_current=False)
    )
    db.execute(stmt)


@app.post("/contracts", response_model=ContractVersionResponse)
def create_contract(
    request: ContractCreateRequest,
    db: Session = Depends(get_db),
) -> ContractVersionResponse:
    contract_id = request.contract_id or uuid.uuid4().hex
    contract = db.get(Contract, contract_id)
    if contract is None:
        contract = Contract(
            contract_id=contract_id,
            contract_type=request.contract_type,
            contract_metadata=request.metadata,
        )
        db.add(contract)

    version_number = _next_version(db, contract_id)
    _set_versions_not_current(db, contract_id)
    version = ContractVersion(
        contract_id=contract_id,
        version_number=version_number,
        workflow_state=request.workflow_state,
        is_current=True,
        etag=uuid.uuid4().hex,
    )
    db.add(version)
    db.commit()
    db.refresh(version)

    return ContractVersionResponse(
        contract_id=version.contract_id,
        version_number=version.version_number,
        workflow_state=version.workflow_state,
        is_current=version.is_current,
        etag=version.etag,
    )


@app.get("/contracts/{contract_id}/versions/{version_number}", response_model=ContractVersionResponse)
def get_contract_version(
    contract_id: str,
    version_number: int,
    db: Session = Depends(get_db),
) -> ContractVersionResponse:
    version = _get_version(db, contract_id, version_number)
    return _version_to_response(version)


@app.get(
    "/contracts/{contract_id}/versions/{version_number}/parameters",
    response_model=list[ContractParameterResponse],
)
def get_contract_parameters(
    contract_id: str,
    version_number: int,
    db: Session = Depends(get_db),
) -> list[ContractParameterResponse]:
    _get_version(db, contract_id, version_number)
    stmt = (
        select(ContractParameter)
        .where(
            ContractParameter.contract_id == contract_id,
            ContractParameter.version_number == version_number,
        )
        .order_by(ContractParameter.parameter_id)
    )
    rows = db.execute(stmt).scalars().all()
    return [
        ContractParameterResponse(
            parameter_id=row.parameter_id,
            parameter_key=row.parameter_key,
            param_group_id=row.param_group_id,
            param_structure_type=row.param_structure_type,
            original_extract=row.original_extract,
            user_override=row.user_override,
            combined_score=row.combined_score,
            spatial_json=row.spatial_json,
        )
        for row in rows
    ]


@app.post("/contracts/{contract_id}/extract", response_model=list[ParameterResponse])
def extract_contract(
    contract_id: str,
    request: ExtractionRequest,
    db: Session = Depends(get_db),
) -> list[ParameterResponse]:
    version_stmt = select(ContractVersion).where(
        ContractVersion.contract_id == contract_id,
        ContractVersion.is_current.is_(True),
    )
    version = db.execute(version_stmt).scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=404, detail="Contract version not found")

    params = run_extraction(
        db,
        contract_id=contract_id,
        version_number=version.version_number,
        contract_text=request.contract_text,
        parameter_keys=request.parameters,
    )
    return [
        ParameterResponse(
            parameter_id=param.parameter_id,
            parameter_key=param.parameter_key,
            original_extract=param.original_extract,
            user_override=param.user_override,
            combined_score=param.combined_score,
        )
        for param in params
    ]


@app.patch("/parameters/{parameter_id}", response_model=ParameterResponse)
def update_parameter(
    parameter_id: int,
    request: UpdateParameterRequest,
    db: Session = Depends(get_db),
) -> ParameterResponse:
    try:
        param = update_user_override(db, parameter_id, request.user_override)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return ParameterResponse(
        parameter_id=param.parameter_id,
        parameter_key=param.parameter_key,
        original_extract=param.original_extract,
        user_override=param.user_override,
        combined_score=param.combined_score,
    )


@app.post("/contracts/{contract_id}/versions/{version_number}/batch-accept")
def batch_accept(
    contract_id: str,
    version_number: int,
    if_match: str | None = Header(None),
    db: Session = Depends(get_db),
) -> dict:
    version = _get_version(db, contract_id, version_number)
    _validate_etag(version, if_match)
    stmt = (
        update(ContractParameter)
        .where(
            ContractParameter.contract_id == contract_id,
            ContractParameter.version_number == version_number,
            ContractParameter.user_override.is_(None),
            ContractParameter.combined_score >= 0.99,
        )
        .values(
            user_override=ContractParameter.original_extract,
            combined_score=1.0,
        )
    )
    result = db.execute(stmt)
    db.commit()
    return {"updated": result.rowcount or 0}

@app.post("/contracts/{contract_id}/submit-for-approval", response_model=ContractVersionResponse)
def submit_for_approval(
    contract_id: str,
    if_match: str | None = Header(None),
    db: Session = Depends(get_db),
) -> ContractVersionResponse:
    """Transitions state from STAGED_DRAFT to PENDING_APPROVAL."""
    stmt = select(ContractVersion).where(
        ContractVersion.contract_id == contract_id,
        ContractVersion.is_current.is_(True),
    )
    version = db.execute(stmt).scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail="Active contract version not found")

    _validate_etag(version, if_match)
        
    version.workflow_state = "PENDING_APPROVAL"
    version.etag = uuid.uuid4().hex
    db.commit()
    db.refresh(version)
    return _version_to_response(version)

@app.post("/contracts/{contract_id}/approve", response_model=ContractVersionResponse)
def approve_contract(
    contract_id: str,
    if_match: str | None = Header(None),
    db: Session = Depends(get_db),
) -> ContractVersionResponse:
    """Operation Head action: Finalizes contract state to PRODUCTION_ACTIVE."""
    stmt = select(ContractVersion).where(
        ContractVersion.contract_id == contract_id,
        ContractVersion.is_current.is_(True),
    )
    version = db.execute(stmt).scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail="Active contract version not found")

    _validate_etag(version, if_match)
        
    if version.workflow_state != "PENDING_APPROVAL":
        raise HTTPException(status_code=400, detail="Contract is not pending approval")
        
    version.workflow_state = "PRODUCTION_ACTIVE"
    version.etag = uuid.uuid4().hex
    db.commit()
    db.refresh(version)
    return _version_to_response(version)

@app.post("/search", response_model=list[SearchResult])
def search_parameters(
    request: SearchRequest,
    db: Session = Depends(get_db),
) -> list[SearchResult]:
    query_vecs = embed_texts([request.query])
    if not query_vecs:
        return []
    query_vec = query_vecs[0]

    stmt = (
        select(
            ContractParameter,
            ContractParameter.vector_embed.l2_distance(query_vec).label("distance"),
        )
        .where(ContractParameter.vector_embed.is_not(None))
        .order_by("distance")
        .limit(request.k)
    )
    rows = db.execute(stmt).all()

    results: list[SearchResult] = []
    for param, distance in rows:
        score = 1.0 / (1.0 + float(distance))
        results.append(
            SearchResult(
                parameter_id=param.parameter_id,
                parameter_key=param.parameter_key,
                original_extract=param.original_extract,
                score=score,
            )
        )
    return results
