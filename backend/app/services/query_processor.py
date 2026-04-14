"""
Stage 1 of the 4-stage retrieval funnel: Query Understanding.

- Resolves pronouns / coreferences in follow-up queries ("it", "that")
- Decomposes comparison queries ("compare X vs Y") into sub-queries
- Embeds the (rewritten) query with Voyage voyage-3 (query mode)
"""
import re
import anthropic
from app.services.embedder import embed_query
from app.config import settings

_anthropic: anthropic.AsyncAnthropic | None = None


def get_anthropic() -> anthropic.AsyncAnthropic:
    global _anthropic
    if _anthropic is None:
        _anthropic = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _anthropic


def _has_references(query: str) -> bool:
    """Detect pronouns and demonstratives that suggest a follow-up query."""
    return bool(re.search(r'\b(it|its|they|them|that|this|those|these|the same|the above)\b', query, re.I))


async def _rewrite_query(query: str, history: list[dict]) -> str:
    """Ask Claude to make the query self-contained given recent conversation."""
    context = "\n".join(f"{m['role']}: {m['content']}" for m in history[-4:])
    client = get_anthropic()
    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": (
                f"Conversation history:\n{context}\n\n"
                f"Original query: {query}\n\n"
                "Rewrite the query to be fully self-contained (resolve all pronouns and references). "
                "Return ONLY the rewritten query, no explanation."
            ),
        }],
    )
    return response.content[0].text.strip()


async def _decompose_query(query: str) -> list[str]:
    """Split a comparison/multi-hop query into atomic sub-queries."""
    # Simple heuristic — Claude call only when explicit comparison signals detected
    comparison_pattern = re.search(r'\b(vs|versus|compare|difference between|how does .+ differ)\b', query, re.I)
    if not comparison_pattern:
        return [query]

    client = get_anthropic()
    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": (
                f"Query: {query}\n\n"
                "Break this into 2–3 atomic search queries. One per line, no bullets, no numbering."
            ),
        }],
    )
    lines = [l.strip() for l in response.content[0].text.strip().split("\n") if l.strip()]
    return lines[:3] if lines else [query]


async def process_query(raw_query: str, conversation_history: list[dict]) -> dict:
    """
    Returns:
        rewritten:   self-contained query string
        sub_queries: list of atomic search queries
        embedding:   Voyage vector for the rewritten query
    """
    rewritten = raw_query

    if conversation_history and _has_references(raw_query):
        rewritten = await _rewrite_query(raw_query, conversation_history)

    sub_queries = await _decompose_query(rewritten)
    embedding = await embed_query(rewritten)

    return {
        "rewritten": rewritten,
        "sub_queries": sub_queries,
        "embedding": embedding,
    }
