"""
embeddings.py — embedding backends + Oracle 23ai vector search helpers.

Supports either sentence-transformers models or a local GGUF embedding model
through llama-cpp-python. The Oracle VECTOR dimension is configured separately
through the project settings so the database column matches the model output.
"""
from __future__ import annotations

import json
import sys
import threading
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.logger import clm_logger

_embed_lock = threading.RLock()

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
        clm_logger.warning(
            "[Embeddings] No SENTENCE_TRANSFORMER_MODEL configured. "
            "Upload will continue without vector embeddings."
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
            clm_logger.info(f"[Embeddings] Loaded GGUF embedding model from {model_path}.")
            return _model
        except ImportError:
            clm_logger.warning(
                "[Embeddings] llama-cpp-python is not installed. Run: uv pip install llama-cpp-python"
            )
            _model = None
            return None
        except Exception as exc:
            clm_logger.error(
                f"[Embeddings] Failed to load GGUF embedding model '{model_path}': {exc}. "
                "Upload will continue without vector embeddings.",
                exc_info=True
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
        clm_logger.warning(
            "[Embeddings] sentence-transformers not installed. "
            "Run: pip install sentence-transformers"
        )
        _model = None
    except Exception as exc:
        clm_logger.error(
            f"[Embeddings] Failed to load embedding model '{raw_model_ref}': {exc}. "
            "Upload will continue without vector embeddings.",
            exc_info=True
        )
        _model = None
    return _model


def embed(text_input: str) -> Optional[List[float]]:
    """
    Returns a float list of length settings.embedding_vector_dim for `text_input`,
    or None if the model is unavailable.
    """
    with _embed_lock:
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
            clm_logger.error(f"[Embeddings] encode error: {exc}", exc_info=True)
            return None


def embed_batch(texts: List[str]) -> List[Optional[List[float]]]:
    """
    Vectorizes a list of strings in a single model call where possible.
    Returns a list of the same length; entries are None if the text is empty
    or if the model is unavailable.
    """
    with _embed_lock:
        model = _get_model()
        if model is None:
            return [None] * len(texts)

        results: List[Optional[List[float]]] = []

        if _model_backend == "llama_cpp":
            # llama_cpp does not expose a native batch encode; fall back to sequential.
            for text in texts:
                results.append(embed(text))
            return results

        # sentence_transformers supports true batch encoding.
        non_empty_indices = [i for i, t in enumerate(texts) if t and t.strip()]
        non_empty_texts = [texts[i] for i in non_empty_indices]

        if not non_empty_texts:
            return [None] * len(texts)

        try:
            vectors = model.encode(non_empty_texts, normalize_embeddings=True, show_progress_bar=False)
        except Exception as exc:
            clm_logger.error(f"[Embeddings] batch encode error: {exc}", exc_info=True)
            return [None] * len(texts)

        # Re-assemble into original index positions.
        output: List[Optional[List[float]]] = [None] * len(texts)
        for result_idx, original_idx in enumerate(non_empty_indices):
            vec = vectors[result_idx]
            output[original_idx] = vec.tolist() if hasattr(vec, "tolist") else list(vec)
        return output


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

    contract_filter = ""
    bind_params: dict = {"top_k": top_k, "query_vec": json.dumps(query_vec)}
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
            VECTOR_DISTANCE(p.vector_embed, TO_VECTOR(:query_vec, {settings.embedding_vector_dim}, FLOAT32), COSINE) AS distance
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
        clm_logger.error(f"[VectorSearch] Oracle VECTOR_DISTANCE query failed: {exc}", exc_info=True)
        return []


async def vector_search_chunks(
    db: AsyncSession,
    query_text: str,
    contract_id: str,
    top_k: int = 5,
) -> List[dict]:
    """
    Cosine similarity search scoped to a single contract's paragraph-level chunks.
    Used by the LangGraph Extractor node to retrieve relevant document context
    without loading the entire document text into the LLM prompt.
    Falls back to empty list if embeddings are unavailable or table is empty.
    """
    query_vec = embed(query_text)
    if query_vec is None:
        return []

    sql = text(f"""
        SELECT
            c.chunk_id,
            c.contract_id,
            c.chunk_index,
            c.chunk_text,
            c.char_start,
            c.char_end,
            c.spatial_json,
            VECTOR_DISTANCE(c.chunk_vector, TO_VECTOR(:query_vec, {settings.embedding_vector_dim}, FLOAT32), COSINE) AS distance
        FROM contract_document_chunks c
        WHERE c.contract_id = :contract_id
          AND c.chunk_vector IS NOT NULL
        ORDER BY distance ASC
        FETCH FIRST :top_k ROWS ONLY
    """)

    try:
        result = await db.execute(sql, {"contract_id": contract_id, "top_k": top_k, "query_vec": json.dumps(query_vec)})
        rows = result.mappings().all()
        return [dict(row) for row in rows]
    except Exception as exc:
        exc_str = str(exc).lower()
        # ORA-00942: table or view does not exist — DDL not yet applied.
        if "942" in exc_str or "does not exist" in exc_str or "table" in exc_str:
            if not getattr(vector_search_chunks, "_ddl_warning_emitted", False):
                clm_logger.warning(
                    "[VectorSearch] 'contract_document_chunks' table not found in Oracle. "
                    "Run the new DDL from schema_oracle26ai.sql (CREATE TABLE contract_document_chunks ...). "
                    "Falling back to document_text head+tail for extraction context."
                )
                vector_search_chunks._ddl_warning_emitted = True  # type: ignore[attr-defined]
        elif "vector" in exc_str:
            if not getattr(vector_search_chunks, "_vector_warning_emitted", False):
                clm_logger.warning(
                    "[VectorSearch] Oracle VECTOR type not supported on this instance. "
                    "Requires Oracle 23ai. Chunk vector search disabled."
                )
                vector_search_chunks._vector_warning_emitted = True  # type: ignore[attr-defined]
        else:
            clm_logger.error(f"[VectorSearch] Chunk vector search failed: {exc}", exc_info=True)
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

    sql = text(f"""
        SELECT
            c.contract_id,
            c.contract_type,
            c.agreement_type,
            c.organization,
            c.uploaded_filename,
            VECTOR_DISTANCE(c.document_vector, TO_VECTOR(:query_vec, {settings.embedding_vector_dim}, FLOAT32), COSINE) AS distance
        FROM contracts_master c
        WHERE c.document_vector IS NOT NULL
        ORDER BY distance ASC
        FETCH FIRST :top_k ROWS ONLY
    """)

    try:
        result = await db.execute(sql, {"top_k": top_k, "query_vec": json.dumps(query_vec)})
        rows = result.mappings().all()
        return [dict(row) for row in rows]
    except Exception as exc:
        clm_logger.error(f"[VectorSearch] Document vector search failed: {exc}", exc_info=True)
        return []