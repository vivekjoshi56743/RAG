"""
Stage 2 of the 4-stage retrieval funnel: Broad Retrieval.

Three signals run in parallel, then fuse with Reciprocal Rank Fusion (RRF):
  1. Dense (vector)   — pgvector HNSW cosine similarity
  2. Sparse (BM25)    — PostgreSQL GIN full-text search
  3. Question match   — question_embedding HNSW cosine similarity

RRF: score = Σ weight_i / (k + rank_i),  k=60
Weights: dense 0.40, sparse 0.30, question 0.30
"""
import asyncio
from uuid import UUID


RRF_K = 60
WEIGHTS = {"dense": 0.40, "sparse": 0.30, "question": 0.30}
CANDIDATE_COUNT = 100


async def retrieve(
    user_id: UUID,
    query_embedding: list[float],
    db,
    document_ids: list[UUID] | None = None,
    folder_id: UUID | None = None,
) -> list[dict]:
    """Run 3-signal retrieval in parallel and return top CANDIDATE_COUNT candidates."""
    dense_task = _dense_retrieval(user_id, query_embedding, db, document_ids, folder_id)
    sparse_task = _sparse_retrieval(user_id, query_embedding, db, document_ids, folder_id)
    question_task = _question_retrieval(user_id, query_embedding, db, document_ids, folder_id)

    dense, sparse, question = await asyncio.gather(dense_task, sparse_task, question_task)

    return _rrf_fusion(dense, sparse, question)


async def _dense_retrieval(user_id, embedding, db, doc_ids, folder_id) -> list[dict]:
    """pgvector HNSW cosine similarity search."""
    # TODO: execute SQL and return [{id, content, document_id, ...}, ...]
    return []


async def _sparse_retrieval(user_id, embedding, db, doc_ids, folder_id) -> list[dict]:
    """PostgreSQL GIN tsvector BM25 search."""
    # TODO: execute SQL with ts_rank and return results
    return []


async def _question_retrieval(user_id, embedding, db, doc_ids, folder_id) -> list[dict]:
    """HNSW search on question_embedding (HyDE — question-to-question matching)."""
    # TODO: execute SQL and return results
    return []


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
