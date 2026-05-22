import json
from typing import Any

from openai import OpenAI

from .config import get_settings

settings = get_settings()
client = OpenAI(base_url=settings.llama_base_url, api_key=settings.llama_api_key)


def _parse_json(content: str) -> Any:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {}


def _normalize_items(data: Any) -> list[dict]:
    if isinstance(data, dict) and "parameters" in data:
        items = data.get("parameters")
    elif isinstance(data, list):
        items = data
    else:
        items = []

    normalized: list[dict] = []
    for idx, item in enumerate(items or []):
        if not isinstance(item, dict):
            continue
        key = item.get("key") or item.get("name") or f"param_{idx + 1}"
        value = item.get("value") or ""
        normalized.append(
            {
                "key": str(key),
                "value": str(value),
                "spatial": item.get("spatial"),
            }
        )
    return normalized


def _iter_paragraph_chunks(text: str, max_chars: int = 3000) -> list[str]:
    paragraphs = [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_size = 0

    for paragraph in paragraphs:
        paragraph_size = len(paragraph)
        if paragraph_size > max_chars:
            if current:
                chunks.append("\n\n".join(current))
                current = []
                current_size = 0
            for start in range(0, paragraph_size, max_chars):
                chunks.append(paragraph[start : start + max_chars])
            continue

        separator = 2 if current else 0
        if current and current_size + separator + paragraph_size > max_chars:
            chunks.append("\n\n".join(current))
            current = [paragraph]
            current_size = paragraph_size
            continue

        if current:
            current_size += separator + paragraph_size
        else:
            current_size = paragraph_size
        current.append(paragraph)

    if current:
        chunks.append("\n\n".join(current))
    return chunks


def extract_parameters(contract_text: str, parameter_keys: list[str] | None = None) -> list[dict]:
    key_hint = ""
    if parameter_keys:
        key_hint = "Return only these keys for this chunk: " + ", ".join(parameter_keys) + "."

    system_prompt = (
        "You extract contract parameters and return JSON only. "
        "Return a JSON object with a 'parameters' array for this chunk only. "
        "Each array item must include: key, value, spatial. "
        "The spatial field can be null when not available."
    )
    chunks = _iter_paragraph_chunks(contract_text)
    results: list[dict] = []

    for chunk in chunks:
        user_prompt = f"{key_hint}\n\nChunk:\n{chunk}"
        response = client.chat.completions.create(
            model=settings.llama_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )

        content = response.choices[0].message.content or "{}"
        data = _parse_json(content)
        items = _normalize_items(data)
        if items:
            results.extend(items)

    return results
