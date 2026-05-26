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
    if isinstance(data, list):
        return data
    return []


async def seed_defaults(session: AsyncSession) -> None:
    rule_count = (
        await session.execute(select(MasterExtractionRule.rule_id).limit(1))
    ).scalar_one_or_none()
    metadata_count = (
        await session.execute(select(MetadataOption.option_id).limit(1))
    ).scalar_one_or_none()

    if rule_count is None:
        for rule in _read_json_file("default_master_rules.json"):
            session.add(MasterExtractionRule(**rule))

    if metadata_count is None:
        for option in _read_json_file("default_metadata_options.json"):
            session.add(MetadataOption(**option))

    await session.commit()
