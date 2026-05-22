from sqlalchemy.orm import Session

from ..embeddings import embed_texts
from ..llm_client import extract_parameters
from ..models import ContractParameter
from ..normalization import normalize_text
from ..scoring import combined_score, cosine_similarity, text_precision


def run_extraction(
    db: Session,
    contract_id: str,
    version_number: int,
    contract_text: str,
    parameter_keys: list[str] | None,
) -> list[ContractParameter]:
    # 1. Extract raw items from all text chunks
    raw_items = extract_parameters(contract_text, parameter_keys=parameter_keys)
    
    # 2. Reconcile Duplicates (Keep the longest extraction value or highest structural fidelity)
    unique_items: dict[str, dict] = {}
    for item in raw_items:
        key = item["key"]
        val = item["value"].strip()
        
        if not val:
            continue
            
        if key in unique_items:
            # If key already exists, update only if the new text string contains more definition
            if len(val) > len(unique_items[key]["value"]):
                unique_items[key] = item
        else:
            unique_items[key] = item

    items = list(unique_items.values())
    values = [item["value"] for item in items]
    embeddings = embed_texts(values) if values else []

    params: list[ContractParameter] = []
    for idx, item in enumerate(items):
        embedding = embeddings[idx] if idx < len(embeddings) else None
        param = ContractParameter(
            contract_id=contract_id,
            version_number=version_number,
            parameter_key=item["key"],
            original_extract=item["value"],
            user_override=None,
            spatial_json=item.get("spatial"),
            combined_score=1.0,
            vector_embed=embedding,
        )
        db.add(param)
        params.append(param)

    db.commit()
    for param in params:
        db.refresh(param)
    return params


def update_user_override(
    db: Session,
    parameter_id: int,
    new_value: str | None,
) -> ContractParameter:
    param = db.get(ContractParameter, parameter_id)
    if param is None:
        raise ValueError("Parameter not found")

    param.user_override = new_value
    original = normalize_text(param.original_extract or "")
    override = normalize_text(new_value or "")
    text_score = text_precision(original, override)

    semantic_score = 0.0
    if param.vector_embed is not None and new_value:
        new_embed = embed_texts([new_value])[0]
        semantic_score = cosine_similarity(param.vector_embed, new_embed)

    param.combined_score = combined_score(text_score, semantic_score)
    db.commit()
    db.refresh(param)
    return param
