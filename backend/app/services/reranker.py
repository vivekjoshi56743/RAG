"""
Stage 3 of the 4-stage retrieval funnel: Cross-Encoder Re-Ranking.

Default: Cohere Rerank 3.5 (~300ms, NDCG@10 = 0.67, $0.002/search)
Fallback: Claude LLM reranker (~2s, NDCG@10 ~0.70) for comparison/multi-hop queries
"""
import cohere
import anthropic
from app.config import settings

_cohere: cohere.AsyncClient | None = None
_anthropic: anthropic.AsyncAnthropic | None = None


def get_cohere() -> cohere.AsyncClient:
    global _cohere
    if _cohere is None:
        _cohere = cohere.AsyncClient(api_key=settings.cohere_api_key)
    return _cohere


def get_anthropic() -> anthropic.AsyncAnthropic:
    global _anthropic
    if _anthropic is None:
        _anthropic = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _anthropic


async def rerank(query: str, chunks: list[dict], top_n: int = 15, use_llm: bool = False) -> list[dict]:
    """Re-rank chunks against query. use_llm=True for complex/comparison queries."""
    if not chunks:
        return []
    if use_llm:
        return await _llm_rerank(query, chunks, top_n)
    return await _cohere_rerank(query, chunks, top_n)


async def _cohere_rerank(query: str, chunks: list[dict], top_n: int) -> list[dict]:
    client = get_cohere()
    response = await client.rerank(
        model="rerank-v3.5",
        query=query,
        documents=[c["content"] for c in chunks],
        top_n=top_n,
        return_documents=False,
    )
    return [
        {**chunks[r.index], "rerank_score": r.relevance_score}
        for r in response.results
    ]


async def _llm_rerank(query: str, chunks: list[dict], top_n: int) -> list[dict]:
    """Ask Claude to score each (query, chunk) pair. Slower but highest quality."""
    client = get_anthropic()
    scored = []
    for chunk in chunks[:top_n * 2]:
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=10,
            messages=[{
                "role": "user",
                "content": (
                    f"Query: {query}\n\nPassage: {chunk['content'][:1000]}\n\n"
                    "Rate relevance 0.0–1.0. Respond with the number only."
                ),
            }],
        )
        try:
            score = float(response.content[0].text.strip())
        except ValueError:
            score = 0.0
        scored.append({**chunk, "rerank_score": score})
    return sorted(scored, key=lambda c: c["rerank_score"], reverse=True)[:top_n]
