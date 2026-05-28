"""
bootstrap.py — Seeds default master rules and metadata options on startup.

Updated to also seed universal rules from default_universal_rules.json.
Universal rules (contract_type="UNIVERSAL", agreement_type="UNIVERSAL") are
applied to every contract regardless of its classification.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import MasterExtractionRule, MetadataOption


SEED_DIR = Path(__file__).resolve().parent.parent / "seed_data"


def _read_json_file(file_name: str) -> List[Dict[str, Any]]:
    file_path = SEED_DIR / file_name
    if not file_path.exists():
        return []
    with file_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, list) else []


async def _seed_master_rules(session: AsyncSession) -> None:
    existing = {
        (row.contract_type, row.agreement_type, row.parameter_head, row.parameter_name)
        for row in (
            await session.execute(
                select(
                    MasterExtractionRule.contract_type,
                    MasterExtractionRule.agreement_type,
                    MasterExtractionRule.parameter_head,
                    MasterExtractionRule.parameter_name,
                )
            )
        ).all()
    }

    rows: List[MasterExtractionRule] = []

    # Seed both the original rules and the new universal + contract-specific rules
    for file_name in ("default_master_rules.json", "default_universal_rules.json"):
        for rule in _read_json_file(file_name):
            key = (
                rule.get("contract_type"),
                rule.get("agreement_type"),
                rule.get("parameter_head"),
                rule.get("parameter_name"),
            )
            if key not in existing:
                rows.append(MasterExtractionRule(**rule))
                existing.add(key)  # prevent dupes within same seed run

    if rows:
        session.add_all(rows)


async def _seed_metadata_options(session: AsyncSession) -> None:
    existing = {
        (row.category, row.value)
        for row in (
            await session.execute(select(MetadataOption.category, MetadataOption.value))
        ).all()
    }

    rows: List[MetadataOption] = []
    for option in _read_json_file("default_metadata_options.json"):
        key = (option.get("category"), option.get("value"))
        if key not in existing:
            rows.append(MetadataOption(**option))

    if rows:
        session.add_all(rows)


async def seed_defaults(session: AsyncSession) -> None:
    await _seed_master_rules(session)
    await _seed_metadata_options(session)
    await session.commit()