"""
Voyage AI voyage-3 embedder (async, batched, contextual prefixing).

- Documents: embed with [metadata prefix] + chunk text, input_type="document"
- Queries:   embed with instruction prefix, input_type="query"
- Fallback:  Cohere embed-v3 if Voyage is unavailable
"""
import voyageai
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings

_client: voyageai.AsyncClient | None = None


def get_client() -> voyageai.AsyncClient:
    global _client
    if _client is None:
        _client = voyageai.AsyncClient(api_key=settings.voyage_api_key)
    return _client


def build_embedding_text(chunk: dict) -> str:
    """Prepend available structural context to improve retrieval accuracy."""
    prefix_parts = []
    if chunk.get("doc_name"):
        prefix_parts.append(f"Document: {chunk['doc_name']}")
    if chunk.get("detected_heading"):
        prefix_parts.append(f"Section: {chunk['detected_heading']}")
    if chunk.get("detected_subheading"):
        prefix_parts.append(f"Subsection: {chunk['detected_subheading']}")
    if chunk.get("doc_summary_short"):
        prefix_parts.append(f"Context: {chunk['doc_summary_short']}")
    prefix = " | ".join(prefix_parts)
    return f"[{prefix}]\n\n{chunk['content']}" if prefix else chunk["content"]


def build_query_text(query: str) -> str:
    return f"Represent this question for retrieving relevant document passages: {query}"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
async def embed_documents(texts: list[str], batch_size: int = 128) -> list[list[float]]:
    """Embed document chunks in batches of batch_size."""
    client = get_client()
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        result = await client.embed(
            batch,
            model="voyage-3",
            input_type="document",
            truncation=True,
        )
        all_embeddings.extend(result.embeddings)
    return all_embeddings


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
async def embed_query(query: str) -> list[float]:
    """Embed a single search query."""
    client = get_client()
    result = await client.embed(
        [build_query_text(query)],
        model="voyage-3",
        input_type="query",
        truncation=True,
    )
    return result.embeddings[0]
