import datetime as dt
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, ForeignKeyConstraint, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import PrimaryKeyConstraint

from .db import Base


class Contract(Base):
    __tablename__ = "contracts"

    contract_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    contract_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    contract_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, nullable=False)


class ContractVersion(Base):
    __tablename__ = "contract_versions"

    contract_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("contracts.contract_id"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    workflow_state: Mapped[str] = mapped_column(String(30), default="STAGED_DRAFT", nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    etag: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, nullable=False)

    __table_args__ = (PrimaryKeyConstraint("contract_id", "version_number"),)


class ContractParameter(Base):
    __tablename__ = "contract_parameters_extracted"

    parameter_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contract_id: Mapped[str] = mapped_column(String(50), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    parameter_key: Mapped[str] = mapped_column(String(200), nullable=False)
    param_group_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    param_structure_type: Mapped[str] = mapped_column(String(20), default="SCALAR", nullable=False)
    original_extract: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_override: Mapped[str | None] = mapped_column(Text, nullable=True)
    spatial_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    combined_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    vector_embed: Mapped[list[float] | None] = mapped_column(Vector(384), nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["contract_id", "version_number"],
            ["contract_versions.contract_id", "contract_versions.version_number"],
        ),
    )
