"""
embeddings.py — embedding backends + Oracle 23ai vector search helpers.

Supports either sentence-transformers models or a local GGUF embedding model
through llama-cpp-python. The Oracle VECTOR dimension is configured separately
through the project settings so the database column matches the model output.
"""
from __future__ import annotations

import json
import sys
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

# ── Model loading (lazy singleton) ────────────────────────────────────────────

_model = None
_model_backend = ""
_model_load_attempted = False


def _get_model():
    global _model, _model_backend, _model_load_attempted
    if _model is not None or _model_load_attempted:
        return _model

    _model_load_attempted = True

    raw_model_ref = (settings.sentence_transformer_model or "").strip()
    if not raw_model_ref:
        print(
            "[Embeddings] No SENTENCE_TRANSFORMER_MODEL configured. "
            "Upload will continue without vector embeddings.",
            file=sys.stderr,
        )
        return None

    model_path = settings.resolve_embedding_model_path()
    if model_path and model_path.is_file() and model_path.suffix.lower() == ".gguf":
        try:
            from llama_cpp import Llama  # type: ignore

            _model = Llama(
                model_path=str(model_path),
                embedding=True,
                n_ctx=2048,
                verbose=False,
            )
            _model_backend = "llama_cpp"
            print(f"[Embeddings] Loaded GGUF embedding model from {model_path}.", file=sys.stderr)
            return _model
        except ImportError:
            print(
                "[Embeddings] llama-cpp-python is not installed. Run: uv pip install llama-cpp-python",
                file=sys.stderr,
            )
            _model = None
            return None
        except Exception as exc:
            print(
                f"[Embeddings] Failed to load GGUF embedding model '{model_path}': {exc}. "
                "Upload will continue without vector embeddings.",
                file=sys.stderr,
            )
            _model = None
            return None

    try:
        from sentence_transformers import SentenceTransformer  # type: ignore

        if model_path and model_path.exists() and model_path.is_dir():
            _model = SentenceTransformer(str(model_path))
        else:
            _model = SentenceTransformer(raw_model_ref)
        _model_backend = "sentence_transformers"
    except ImportError:
        print(
            "[Embeddings] sentence-transformers not installed. "
            "Run: pip install sentence-transformers",
            file=sys.stderr,
        )
        _model = None
    except Exception as exc:
        print(
            f"[Embeddings] Failed to load embedding model '{raw_model_ref}': {exc}. "
            "Upload will continue without vector embeddings.",
            file=sys.stderr,
        )
        _model = None
    return _model


def embed(text_input: str) -> Optional[List[float]]:
    """
    Returns a 384-dim float list for `text_input`, or None if the model
    is unavailable.
    """
    model = _get_model()
    if model is None or not text_input or not text_input.strip():
        return None
    try:
        if _model_backend == "llama_cpp":
            if hasattr(model, "embed"):
                vector = model.embed(text_input, normalize=True)
            elif hasattr(model, "create_embedding"):
                result = model.create_embedding(text_input)
                data = result.get("data", []) if isinstance(result, dict) else []
                vector = data[0].get("embedding") if data else None
            else:
                vector = None

            if vector is None:
                return None
            if hasattr(vector, "tolist"):
                return vector.tolist()
            return list(vector)

        vector = model.encode(text_input, normalize_embeddings=True)
        return vector.tolist()
    except Exception as exc:
        print(f"[Embeddings] encode error: {exc}", file=sys.stderr)
        return None


def serialize(vector: Optional[List[float]]) -> Optional[str]:
    """Serializes a vector to JSON string for CLOB storage (ORM path)."""
    if vector is None:
        return None
    return json.dumps(vector)


# ── Oracle 23ai vector similarity search ──────────────────────────────────────

async def vector_search_parameters(
    db: AsyncSession,
    query_text: str,
    contract_ids: Optional[List[str]] = None,
    top_k: int = 5,
) -> List[dict]:
    """
    Searches contract_parameters_extracted using Oracle 23ai VECTOR_DISTANCE
    with cosine similarity.

    Falls back to empty list if embeddings are unavailable.
    """
    query_vec = embed(query_text)
    if query_vec is None:
        return []

    # Oracle 23ai native vector literal syntax: TO_VECTOR('[0.1, 0.2, ...]')
    vec_literal = f"TO_VECTOR('{json.dumps(query_vec)}')"

    contract_filter = ""
    bind_params: dict = {"top_k": top_k}
    if contract_ids:
        placeholders = ", ".join(f":cid{i}" for i in range(len(contract_ids)))
        contract_filter = f"AND p.contract_id IN ({placeholders})"
        for i, cid in enumerate(contract_ids):
            bind_params[f"cid{i}"] = cid

    sql = text(f"""
        SELECT
            p.parameter_id,
            p.contract_id,
            p.header_name,
            p.param_name,
            p.original_extract,
            p.user_override,
            p.citation_text,
            p.citation_start,
            p.citation_end,
            p.spatial_json,
            p.source_query,
            p.is_user_added,
            p.is_verified,
            VECTOR_DISTANCE(p.vector_embed, {vec_literal}, COSINE) AS distance
        FROM contract_parameters_extracted p
        WHERE p.vector_embed IS NOT NULL
        {contract_filter}
        ORDER BY distance ASC
        FETCH FIRST :top_k ROWS ONLY
    """)

    try:
        result = await db.execute(sql, bind_params)
        rows = result.mappings().all()
        return [dict(row) for row in rows]
    except Exception as exc:
        print(f"[VectorSearch] Oracle VECTOR_DISTANCE query failed: {exc}", file=sys.stderr)
        return []


async def vector_search_documents(
    db: AsyncSession,
    query_text: str,
    top_k: int = 5,
) -> List[dict]:
    """
    Searches contracts_master.document_vector using VECTOR_DISTANCE.
    Returns top-k contracts by semantic similarity to the query.
    """
    query_vec = embed(query_text)
    if query_vec is None:
        return []

    vec_literal = f"TO_VECTOR('{json.dumps(query_vec)}')"

    sql = text(f"""
        SELECT
            c.contract_id,
            c.contract_type,
            c.agreement_type,
            c.organization,
            c.uploaded_filename,
            VECTOR_DISTANCE(c.document_vector, {vec_literal}, COSINE) AS distance
        FROM contracts_master c
        WHERE c.document_vector IS NOT NULL
        ORDER BY distance ASC
        FETCH FIRST :top_k ROWS ONLY
    """)

    try:
        result = await db.execute(sql, {"top_k": top_k})
        rows = result.mappings().all()
        return [dict(row) for row in rows]
    except Exception as exc:
        print(f"[VectorSearch] Document vector search failed: {exc}", file=sys.stderr)
        return []