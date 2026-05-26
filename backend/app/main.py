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
from app.routes import assistant, contracts, dashboard, maintenance, metadata, rules, verification
from app.services.bootstrap import seed_defaults
from app.services.llm import azure_llm


ORACLE_VECTOR_REQUIRED_DIMENSIONS = {
    "contracts_master": {"document_vector": settings.embedding_vector_dim},
    "contract_parameters_extracted": {"vector_embed": settings.embedding_vector_dim},
}

ORACLE_IDENTITY_REQUIRED_COLUMNS = {
    "contract_parameters_extracted": {"parameter_id"},
    "contract_audit_trail": {"audit_id"},
    "master_extraction_rules": {"rule_id"},
    "metadata_options": {"option_id"},
}


def _ensure_schema(sync_conn):
    inspector = inspect(sync_conn)

    if sync_conn.dialect.name == "oracle":
        needs_rebuild = False

        for table_name, identity_columns in ORACLE_IDENTITY_REQUIRED_COLUMNS.items():
            if not inspector.has_table(table_name):
                continue
            existing_columns = {
                col["name"].lower(): col for col in inspector.get_columns(table_name)
            }
            if any(existing_columns.get(column, {}).get("identity") is None for column in identity_columns):
                needs_rebuild = True
                break

        if not needs_rebuild:
            for table_name, expected_dimensions in ORACLE_VECTOR_REQUIRED_DIMENSIONS.items():
                if not inspector.has_table(table_name):
                    continue
                existing_columns = {
                    col["name"].lower(): col for col in inspector.get_columns(table_name)
                }
                for column_name, expected_dim in expected_dimensions.items():
                    column_info = existing_columns.get(column_name)
                    column_type = column_info.get("type") if column_info else None
                    actual_dim = getattr(column_type, "dim", None) if column_type is not None else None
                    if actual_dim != expected_dim:
                        needs_rebuild = True
                        break
                if needs_rebuild:
                    break

        if needs_rebuild:
            Base.metadata.drop_all(sync_conn)


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        async with engine.begin() as conn:
            await conn.run_sync(_ensure_schema)
            await conn.run_sync(Base.metadata.create_all)

        async with AsyncSessionLocal() as session:
            await seed_defaults(session)

        yield
    finally:
        await azure_llm.aclose()


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
app.include_router(assistant.router, prefix=settings.api_prefix)
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