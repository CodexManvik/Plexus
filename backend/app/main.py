from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import settings
from app.database import AsyncSessionLocal, Base, engine, get_database_driver
from app.routes import contracts, dashboard, maintenance, metadata, rules, verification
from app.services.bootstrap import seed_defaults


SQLITE_REQUIRED_COLUMNS = {
    "contract_id",
    "organization",
    "business_unit",
    "location",
    "department",
    "customer_partner_name",
    "financial_year",
    "contract_type",
    "agreement_type",
    "additional_info",
    "contract_number",
    "version_amendment_number",
    "execution_type",
    "governing_entity",
    "jurisdiction",
    "governing_law",
    "legal_names_of_parties",
    "registered_addresses",
    "cin_registration_numbers",
    "authorized_signatories",
    "contact_persons",
    "party_roles",
    "affiliates_subsidiaries_involved",
    "effective_date",
}

ORACLE_IDENTITY_REQUIRED_COLUMNS = {
    "contract_parameters_extracted": {"parameter_id"},
    "contract_audit_trail": {"audit_id"},
    "master_extraction_rules": {"rule_id"},
    "metadata_options": {"option_id"},
}


def _ensure_schema(sync_conn):
    inspector = inspect(sync_conn)
    if sync_conn.dialect.name == "sqlite" and inspector.has_table("contracts_master"):
        existing_columns = {col["name"] for col in inspector.get_columns("contracts_master")}
        if not SQLITE_REQUIRED_COLUMNS.issubset(existing_columns):
            Base.metadata.drop_all(sync_conn)
    elif sync_conn.dialect.name == "oracle":
        for table_name, identity_columns in ORACLE_IDENTITY_REQUIRED_COLUMNS.items():
            if not inspector.has_table(table_name):
                continue
            existing_columns = {
                col["name"].lower(): col for col in inspector.get_columns(table_name)
            }
            if any(existing_columns.get(column, {}).get("identity") is None for column in identity_columns):
                Base.metadata.drop_all(sync_conn)
                break
    Base.metadata.create_all(sync_conn)


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(_ensure_schema)

    async with AsyncSessionLocal() as session:
        await seed_defaults(session)

    yield


app = FastAPI(
    title=settings.app_name,
    description=(
        "Contract lifecycle ingestion, rule-based extraction, verification, "
        "approval, and dashboard APIs."
    ),
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(contracts.router, prefix=settings.api_prefix)
app.include_router(dashboard.router, prefix=settings.api_prefix)
app.include_router(rules.router, prefix=settings.api_prefix)
app.include_router(metadata.router, prefix=settings.api_prefix)
app.include_router(verification.router, prefix=settings.api_prefix)
app.include_router(maintenance.router, prefix=settings.api_prefix)


@app.get(f"{settings.api_prefix}/health", tags=["System Diagnostics"])
async def health_diagnostics():
    return {
        "status": "operational",
        "environment": settings.app_env,
        "database_driver": get_database_driver(),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
