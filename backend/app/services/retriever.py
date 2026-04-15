"""
Stage 2 of the 4-stage retrieval funnel: Broad Retrieval.

Runs dense/sparse/question retrieval, then fuses with Reciprocal Rank Fusion (RRF):
  1. Dense (vector)   — pgvector HNSW cosine similarity
  2. Sparse (BM25)    — PostgreSQL GIN full-text search
  3. Question match   — question_embedding HNSW cosine similarity

RRF: score = Σ weight_i / (k + rank_i),  k=60
Weights: dense 0.40, sparse 0.30, question 0.30
"""
from uuid import UUID

from sqlalchemy import text


RRF_K = 60
WEIGHTS = {"dense": 0.40, "sparse": 0.30, "question": 0.30}
CANDIDATE_COUNT = 100
SIGNAL_LIMIT = 40


async def retrieve(
    user_id: UUID,
    query_text: str,
    query_embedding: list[float],
    db,
    document_ids: list[UUID] | None = None,
    folder_id: UUID | None = None,
) -> list[dict]:
    """
    Run 3-signal retrieval and return top CANDIDATE_COUNT candidates.

    Note: this executes sequentially for a shared asyncpg session/connection safety.
    """
    dense = await _dense_retrieval(user_id, query_embedding, db, document_ids, folder_id)
    sparse = await _sparse_retrieval(user_id, query_text, db, document_ids, folder_id)
    question = await _question_retrieval(user_id, query_embedding, db, document_ids, folder_id)

    return _rrf_fusion(dense, sparse, question)


async def _dense_retrieval(user_id, embedding, db, doc_ids, folder_id) -> list[dict]:
    """pgvector HNSW cosine similarity search."""
    params = _build_common_params(user_id, doc_ids, folder_id)
    params["query_embedding"] = _vector_literal(embedding)

    rows = (
        await db.execute(
            text(
                f"""
                SELECT
                    c.id,
                    c.document_id,
                    c.chunk_index,
                    c.content,
                    c.page_number,
                    c.section_heading,
                    c.source_type,
                    d.name AS doc_name,
                    d.file_path,
                    d.mime_type,
                    d.document_type,
                    1 - (c.embedding <=> CAST(:query_embedding AS vector)) AS signal_score
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE {_access_filter_sql()}
                    AND (CAST(:folder_id AS uuid) IS NULL OR d.folder_id = CAST(:folder_id AS uuid))
                    AND (:use_doc_filter = false OR c.document_id = ANY(:doc_ids))
                    AND c.embedding IS NOT NULL
                ORDER BY c.embedding <=> CAST(:query_embedding AS vector)
                LIMIT {SIGNAL_LIMIT}
                """
            ),
            params,
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def _sparse_retrieval(user_id, query_text, db, doc_ids, folder_id) -> list[dict]:
    """PostgreSQL GIN tsvector BM25 search."""
    params = _build_common_params(user_id, doc_ids, folder_id)
    params["query"] = query_text

    rows = (
        await db.execute(
            text(
                f"""
                SELECT
                    c.id,
                    c.document_id,
                    c.chunk_index,
                    c.content,
                    c.page_number,
                    c.section_heading,
                    c.source_type,
                    d.name AS doc_name,
                    d.file_path,
                    d.mime_type,
                    d.document_type,
                    ts_rank(c.tsv, plainto_tsquery('english', :query)) AS signal_score
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE {_access_filter_sql()}
                    AND (CAST(:folder_id AS uuid) IS NULL OR d.folder_id = CAST(:folder_id AS uuid))
                    AND (:use_doc_filter = false OR c.document_id = ANY(:doc_ids))
                    AND c.tsv @@ plainto_tsquery('english', :query)
                ORDER BY signal_score DESC
                LIMIT {SIGNAL_LIMIT}
                """
            ),
            params,
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def _question_retrieval(user_id, embedding, db, doc_ids, folder_id) -> list[dict]:
    """HNSW search on question_embedding (HyDE — question-to-question matching)."""
    params = _build_common_params(user_id, doc_ids, folder_id)
    params["query_embedding"] = _vector_literal(embedding)
    rows = (
        await db.execute(
            text(
                f"""
                SELECT
                    c.id,
                    c.document_id,
                    c.chunk_index,
                    c.content,
                    c.page_number,
                    c.section_heading,
                    c.source_type,
                    d.name AS doc_name,
                    d.file_path,
                    d.mime_type,
                    d.document_type,
                    1 - (c.question_embedding <=> CAST(:query_embedding AS vector)) AS signal_score
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE {_access_filter_sql()}
                    AND (CAST(:folder_id AS uuid) IS NULL OR d.folder_id = CAST(:folder_id AS uuid))
                    AND (:use_doc_filter = false OR c.document_id = ANY(:doc_ids))
                    AND c.question_embedding IS NOT NULL
                ORDER BY c.question_embedding <=> CAST(:query_embedding AS vector)
                LIMIT {SIGNAL_LIMIT}
                """
            ),
            params,
        )
    ).mappings().all()
    return [dict(r) for r in rows]


def _rrf_fusion(dense: list[dict], sparse: list[dict], question: list[dict]) -> list[dict]:
    """Merge three ranked lists with Reciprocal Rank Fusion."""
    scores: dict[str, float] = {}
    all_chunks: dict[str, dict] = {}

    for signal, results, weight in [
        ("dense", dense, WEIGHTS["dense"]),
        ("sparse", sparse, WEIGHTS["sparse"]),
        ("question", question, WEIGHTS["question"]),
    ]:
        for rank, chunk in enumerate(results):
            cid = str(chunk["id"])
            all_chunks[cid] = chunk
            scores[cid] = scores.get(cid, 0.0) + weight / (RRF_K + rank + 1)

    ranked = sorted(scores.keys(), key=lambda cid: scores[cid], reverse=True)
    return [{**all_chunks[cid], "rrf_score": scores[cid]} for cid in ranked[:CANDIDATE_COUNT]]


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{float(v):.8f}" for v in values) + "]"


def _build_common_params(user_id: UUID, doc_ids: list[UUID] | None, folder_id: UUID | None) -> dict:
    return {
        "user_id": str(user_id),
        "doc_ids": [str(d) for d in (doc_ids or [])],
        "use_doc_filter": bool(doc_ids),
        "folder_id": str(folder_id) if folder_id else None,
    }


def _access_filter_sql() -> str:
    return """
    (
        d.user_id = CAST(:user_id AS uuid)
        OR EXISTS (
            SELECT 1
            FROM permissions p
            WHERE p.grantee_id = CAST(:user_id AS uuid)
              AND (
                    p.document_id = d.id
                    OR (p.folder_id IS NOT NULL AND p.folder_id = d.folder_id)
              )
        )
    )
    """
