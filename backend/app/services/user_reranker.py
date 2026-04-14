"""
Stage 4 of the 4-stage retrieval funnel: User-Signal Re-Ranking.

Applies personalized preference scores based on:
  - Direct chunk preference (has this user engaged with this chunk before?)
  - Document-level affinity (does this user interact with this document often?)
  - Similar-query collaborative filtering (what chunks did they prefer for similar queries?)
  - Re-ranker base score (preserved from Stage 3)

Cold-start safe: skips for users with < 10 feedback signals.
"""
import asyncio
import math
from uuid import UUID


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

    chunk_prefs, doc_prefs, similar_prefs = await asyncio.gather(
        _get_chunk_preferences(user_id, chunk_ids, db),
        _get_doc_preferences(user_id, doc_ids, db),
        _get_similar_query_preferences(user_id, query_embedding, chunk_ids, db),
    )

    for chunk in chunks:
        cid = chunk["id"]
        did = chunk["document_id"]
        chunk["final_score"] = (
            WEIGHTS["rerank_score"] * chunk.get("rerank_score", 0.5) +
            WEIGHTS["chunk_pref"] * _sigmoid(chunk_prefs.get(cid, 0.0)) +
            WEIGHTS["doc_pref"] * _sigmoid(doc_prefs.get(did, 0.0)) +
            WEIGHTS["similar_query"] * _sigmoid(similar_prefs.get(cid, 0.0))
        )

    return sorted(chunks, key=lambda c: c["final_score"], reverse=True)[:top_n]


async def _get_feedback_count(user_id: UUID, db) -> int:
    # TODO: SELECT COUNT(*) FROM user_feedback WHERE user_id = :uid
    return 0


async def _get_chunk_preferences(user_id: UUID, chunk_ids: list, db) -> dict:
    # TODO: query user_chunk_preferences materialized view
    return {}


async def _get_doc_preferences(user_id: UUID, doc_ids: list, db) -> dict:
    # TODO: query user_document_preferences materialized view
    return {}


async def _get_similar_query_preferences(user_id: UUID, query_embedding: list[float], chunk_ids: list, db) -> dict:
    # TODO: find similar past queries (cosine > 0.75) and aggregate their preferred chunks
    return {}
