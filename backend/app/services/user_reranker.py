"""
Stage 4 of the 4-stage retrieval funnel: User-Signal Re-Ranking.

Applies personalized preference scores based on:
  - Direct chunk preference (has this user engaged with this chunk before?)
  - Document-level affinity (does this user interact with this document often?)
  - Similar-query collaborative filtering (what chunks did they prefer for similar queries?)
  - Re-ranker base score (preserved from Stage 3)

Cold-start safe: skips for users with < 10 feedback signals.
"""
import math
from uuid import UUID

from sqlalchemy import text


COLD_START_THRESHOLD = 10

WEIGHTS = {
    "rerank_score": 0.25,
    "chunk_pref": 0.30,
    "doc_pref": 0.15,
    "similar_query": 0.30,
}


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


async def apply_user_signals(
    user_id: UUID,
    query_embedding: list[float],
    chunks: list[dict],
    db,
    top_n: int = 8,
) -> list[dict]:
    """Apply personalized re-ranking. Returns top_n chunks."""
    feedback_count = await _get_feedback_count(user_id, db)
    if feedback_count < COLD_START_THRESHOLD:
        return chunks[:top_n]

    chunk_ids = [c["id"] for c in chunks]
    doc_ids = [c["document_id"] for c in chunks]

    # Run sequentially on the same DB session/connection.
    # asyncpg does not allow overlapping operations on one connection.
    chunk_prefs = await _get_chunk_preferences(user_id, chunk_ids, db)
    doc_prefs = await _get_doc_preferences(user_id, doc_ids, db)
    similar_prefs = await _get_similar_query_preferences(user_id, query_embedding, chunk_ids, db)

    for chunk in chunks:
        cid = str(chunk["id"])
        did = str(chunk["document_id"])
        chunk["final_score"] = (
            WEIGHTS["rerank_score"] * chunk.get("rerank_score", 0.5) +
            WEIGHTS["chunk_pref"] * _sigmoid(chunk_prefs.get(cid, 0.0)) +
            WEIGHTS["doc_pref"] * _sigmoid(doc_prefs.get(did, 0.0)) +
            WEIGHTS["similar_query"] * _sigmoid(similar_prefs.get(cid, 0.0))
        )

    return sorted(chunks, key=lambda c: c["final_score"], reverse=True)[:top_n]


async def _get_feedback_count(user_id: UUID, db) -> int:
    count = (
        await db.execute(
            text("SELECT COUNT(*) FROM user_feedback WHERE user_id = :uid"),
            {"uid": str(user_id)},
        )
    ).scalar_one()
    return int(count or 0)


async def _get_chunk_preferences(user_id: UUID, chunk_ids: list, db) -> dict:
    if not chunk_ids:
        return {}
    rows = (
        await db.execute(
            text(
                """
                SELECT chunk_id, preference_score
                FROM user_chunk_preferences
                WHERE user_id = :uid
                  AND chunk_id = ANY(:chunk_ids)
                """
            ),
            {"uid": str(user_id), "chunk_ids": [str(cid) for cid in chunk_ids]},
        )
    ).mappings().all()
    return {str(r["chunk_id"]): float(r["preference_score"] or 0.0) for r in rows}


async def _get_doc_preferences(user_id: UUID, doc_ids: list, db) -> dict:
    if not doc_ids:
        return {}
    rows = (
        await db.execute(
            text(
                """
                SELECT document_id, doc_preference_score
                FROM user_document_preferences
                WHERE user_id = :uid
                  AND document_id = ANY(:doc_ids)
                """
            ),
            {"uid": str(user_id), "doc_ids": [str(did) for did in doc_ids]},
        )
    ).mappings().all()
    return {str(r["document_id"]): float(r["doc_preference_score"] or 0.0) for r in rows}


async def _get_similar_query_preferences(user_id: UUID, query_embedding: list[float], chunk_ids: list, db) -> dict:
    if not chunk_ids or not query_embedding:
        return {}

    query_vec = "[" + ",".join(f"{float(v):.8f}" for v in query_embedding) + "]"
    rows = (
        await db.execute(
            text(
                """
                SELECT uf.chunk_id, SUM(uf.signal_weight) AS score
                FROM user_feedback uf
                WHERE uf.user_id = :uid
                  AND uf.chunk_id = ANY(:chunk_ids)
                  AND uf.query_embedding IS NOT NULL
                  AND (uf.query_embedding <=> CAST(:query_vec AS vector)) <= 0.25
                GROUP BY uf.chunk_id
                """
            ),
            {
                "uid": str(user_id),
                "chunk_ids": [str(cid) for cid in chunk_ids],
                "query_vec": query_vec,
            },
        )
    ).mappings().all()
    return {str(r["chunk_id"]): float(r["score"] or 0.0) for r in rows}
