"""Create a dimension-aware pgvector HNSW index for half-precision candidates."""

from __future__ import annotations

from sqlalchemy import Engine, text


def ensure_halfvec_hnsw_index(engine: Engine, collection_name: str) -> int | None:
    """Index vectors up to 4,000 dimensions; return the indexed dimension if present."""
    try:
        with engine.begin() as conn:
            dimension = conn.execute(
                text(
                    """
                    SELECT vector_dims(e.embedding)
                    FROM langchain_pg_embedding e
                    JOIN langchain_pg_collection c ON c.uuid = e.collection_id
                    WHERE c.name = :collection_name
                    LIMIT 1
                    """
                ),
                {"collection_name": collection_name},
            ).scalar()
            if dimension is None:
                return None

            dimension = int(dimension)
            if dimension > 4000:
                return None

            index_name = f"idx_lc_embedding_halfvec_hnsw_{dimension}"
            conn.execute(
                text(
                    f"""
                    CREATE INDEX IF NOT EXISTS {index_name}
                    ON langchain_pg_embedding
                    USING hnsw ((embedding::halfvec({dimension})) halfvec_cosine_ops)
                    WHERE vector_dims(embedding) = {dimension}
                    """
                )
            )
            return dimension
    except Exception:
        return None
