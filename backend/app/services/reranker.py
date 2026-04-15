"""
Stage 3 of the 4-stage retrieval funnel: Cross-Encoder Re-Ranking.

Primary: Vertex AI Ranking API
Fallback: Provider-routed LLM reranker (Anthropic/Vertex via llm_provider)
"""
import json

import google.auth
from google.auth.transport.requests import Request as GoogleAuthRequest
import requests

from app.config import settings
from app.services.llm_provider import complete_text


def _get_access_token() -> str:
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    credentials.refresh(GoogleAuthRequest())
    return credentials.token


def _vertex_rank(query: str, chunks: list[dict], top_n: int) -> list[dict]:
    if not settings.vertex_ranking_config:
        raise ValueError("VERTEX_RANKING_CONFIG is not configured")

    token = _get_access_token()
    url = f"https://discoveryengine.googleapis.com/v1alpha/{settings.vertex_ranking_config}:rank"
    payload = {
        "model": settings.vertex_ranking_model,
        "query": query,
        "records": [{"id": str(i), "content": c["content"][:4000]} for i, c in enumerate(chunks)],
        "topN": top_n,
    }
    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    ranked_records = data.get("records", [])
    if not ranked_records:
        return chunks[:top_n]

    ordered: list[dict] = []
    used_ids: set[int] = set()
    for record in ranked_records:
        try:
            idx = int(record.get("id", "-1"))
        except ValueError:
            continue
        if idx < 0 or idx >= len(chunks) or idx in used_ids:
            continue
        score = float(record.get("score", 0.0))
        ordered.append({**chunks[idx], "rerank_score": score})
        used_ids.add(idx)

    ordered.extend(chunks[i] for i in range(len(chunks)) if i not in used_ids)
    return ordered[:top_n]


async def rerank(query: str, chunks: list[dict], top_n: int = 15, use_llm: bool = False) -> list[dict]:
    """Re-rank chunks using Vertex Ranking API, with LLM fallback."""
    if not chunks:
        return []
    if use_llm:
        return await _llm_rerank(query, chunks, top_n)
    try:
        return _vertex_rank(query, chunks, top_n)
    except Exception:
        return await _llm_rerank(query, chunks, top_n)


async def _llm_rerank(query: str, chunks: list[dict], top_n: int) -> list[dict]:
    """LLM-based fallback reranker via provider layer."""
    numbered = "\n\n".join(f"[{i}] {c['content'][:400]}" for i, c in enumerate(chunks[: max(top_n * 2, 20)]))
    prompt = (
        "You are a relevance ranking assistant.\n\n"
        f"Query: {query}\n\n"
        f"Passages:\n{numbered}\n\n"
        "Return a JSON array of passage indices ordered from most to least relevant. "
        "Return ONLY JSON. Example: [3,0,7,1]"
    )
    text, _provider = await complete_text("rerank", prompt, max_tokens=256, temperature=0.0)
    try:
        indices = json.loads(text.strip())
        reranked = [chunks[i] for i in indices if isinstance(i, int) and 0 <= i < len(chunks)]
        ranked_set = set(i for i in indices if isinstance(i, int))
        reranked.extend([c for i, c in enumerate(chunks) if i not in ranked_set])
        return reranked[:top_n]
    except Exception:
        return chunks[:top_n]
