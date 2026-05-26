from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import settings
from app.database import AsyncSessionLocal, Base, engine, get_database_driver
from app.routes import assistant, contracts, dashboard, maintenance, metadata, rules, verification
from app.services.bootstrap import seed_defaults


@asynccontextmanager
async def lifespan(_: FastAPI):
    # On Oracle 23ai we let the schema_oracle23ai.sql DDL own the schema.
    # Here we only ensure tables exist (idempotent create_all won't drop anything).
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

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