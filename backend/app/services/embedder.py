"""
Vertex AI embedder (async, batched, contextual prefixing).

- Documents: task_type="RETRIEVAL_DOCUMENT"
- Queries:   task_type="RETRIEVAL_QUERY"
- Model:     text-embedding-005 (default)
"""
import asyncio
import logging
import vertexai
from google.api_core.exceptions import InvalidArgument
from tenacity import retry, stop_after_attempt, wait_exponential
from vertexai.language_models import TextEmbeddingInput, TextEmbeddingModel

from app.config import settings
from app.services.model_profiles import get_model_profile

_model: TextEmbeddingModel | None = None
_vertex_initialized = False
logger = logging.getLogger(__name__)


def _profile() -> dict:
    return get_model_profile(settings.embedding_model_profile)


def _embedding_chars_per_token() -> int:
    profile = _profile()
    return max(1, settings.embedding_chars_per_token or profile["embedding_chars_per_token"])


def _embedding_max_tokens_per_input() -> int:
    profile = _profile()
    return max(1, settings.embedding_max_tokens_per_input or profile["embedding_max_tokens_per_input"])


def _embedding_max_tokens_per_request() -> int:
    profile = _profile()
    return max(1, settings.embedding_max_tokens_per_request or profile["embedding_max_tokens_per_request"])


def _embedding_max_items_per_request() -> int:
    profile = _profile()
    return max(1, settings.embedding_max_items_per_request or profile["embedding_max_items_per_request"])


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _embedding_chars_per_token())


def _truncate_for_input_limit(text: str) -> str:
    max_chars = _embedding_max_tokens_per_input() * _embedding_chars_per_token()
    if len(text) <= max_chars:
        return text
    logger.warning(
        "Truncating embedding input from %s to %s chars (model profile=%s)",
        len(text),
        max_chars,
        settings.embedding_model_profile,
    )
    return text[:max_chars]


def _is_token_limit_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "token count" in message and "supports up to" in message


def _build_batches(texts: list[str], max_items: int) -> list[list[str]]:
    request_token_budget = _embedding_max_tokens_per_request()
    normalized = [_truncate_for_input_limit(t) for t in texts]
    batches: list[list[str]] = []
    current: list[str] = []
    current_tokens = 0

    for text in normalized:
        token_estimate = _estimate_tokens(text)
        exceeds_count = len(current) >= max_items
        exceeds_tokens = current and (current_tokens + token_estimate > request_token_budget)

        if exceeds_count or exceeds_tokens:
            batches.append(current)
            current = []
            current_tokens = 0

        current.append(text)
        current_tokens += token_estimate

    if current:
        batches.append(current)

    return batches


def _ensure_vertex_initialized() -> None:
    global _vertex_initialized
    if _vertex_initialized:
        return
    project = settings.vertex_project_id or settings.firebase_project_id
    if not project:
        raise ValueError("vertex_project_id (or firebase_project_id fallback) must be set")
    vertexai.init(project=project, location=settings.vertex_location)
    _vertex_initialized = True


def get_model() -> TextEmbeddingModel:
    global _model
    if _model is None:
        _ensure_vertex_initialized()
        _model = TextEmbeddingModel.from_pretrained(settings.vertex_embedding_model)
    return _model


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
    return query.strip()


def _embed_sync(texts: list[str], task_type: str) -> list[list[float]]:
    model = get_model()
    inputs = [TextEmbeddingInput(text=t, task_type=task_type) for t in texts]
    results = model.get_embeddings(inputs, output_dimensionality=settings.embedding_dimensions)
    return [r.values for r in results]


async def _embed_batch_resilient(texts: list[str], task_type: str) -> list[list[float]]:
    try:
        return await asyncio.to_thread(_embed_sync, texts, task_type)
    except InvalidArgument as exc:
        if _is_token_limit_error(exc) and len(texts) > 1:
            midpoint = max(1, len(texts) // 2)
            left = await _embed_batch_resilient(texts[:midpoint], task_type)
            right = await _embed_batch_resilient(texts[midpoint:], task_type)
            return left + right
        raise


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
async def embed_documents(texts: list[str], batch_size: int = 250) -> list[list[float]]:
    """Embed document chunks using token-aware dynamic batching."""
    if not texts:
        return []

    max_items = min(max(1, batch_size), _embedding_max_items_per_request())
    all_embeddings: list[list[float]] = []

    for batch in _build_batches(texts, max_items=max_items):
        all_embeddings.extend(await _embed_batch_resilient(batch, "RETRIEVAL_DOCUMENT"))

    return all_embeddings


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
async def embed_query(query: str) -> list[float]:
    """Embed a single search query."""
    vectors = await _embed_batch_resilient([_truncate_for_input_limit(build_query_text(query))], "RETRIEVAL_QUERY")
    return vectors[0]
