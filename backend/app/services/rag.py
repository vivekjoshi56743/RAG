"""
Full 4-stage RAG pipeline orchestration.

  Stage 1: Query Understanding   (rewrite + decompose + embed)
  Stage 2: Broad Retrieval       (dense + sparse + question → RRF → top 100)
  Stage 3: Cross-Encoder Rerank  (Cohere Rerank 3.5 → top 15)
  Stage 4: User Signal Rerank    (preference scoring → top 8)

  Context Assembly → LLM Generation (streaming SSE)
"""
import asyncio
from uuid import UUID

from app.services.query_processor import process_query
from app.services.retriever import retrieve
from app.services.reranker import rerank
from app.services.user_reranker import apply_user_signals
import anthropic
from app.config import settings

SYSTEM_PROMPT = """You are a helpful research assistant with access to a knowledge base.
Answer the user's question using ONLY the provided sources.
Cite sources inline as [Source N] whenever you use information from them.
If the answer is not in the sources, say so clearly."""


async def run_rag_pipeline(
    user_id: UUID,
    query: str,
    conversation_history: list[dict],
    db,
    document_ids: list[UUID] | None = None,
    folder_id: UUID | None = None,
) -> tuple[list[dict], str]:
    """
    Returns (chunks, assembled_prompt) for streaming to the LLM.
    Call stream_response() separately to get the SSE stream.
    """
    # Stage 1
    query_data = await process_query(query, conversation_history)

    # Stage 2
    candidates = await retrieve(
        user_id=user_id,
        query_embedding=query_data["embedding"],
        db=db,
        document_ids=document_ids,
        folder_id=folder_id,
    )

    # Stage 3 — use LLM reranker for comparison queries (multiple sub-queries)
    use_llm = len(query_data["sub_queries"]) > 1
    reranked = await rerank(query_data["rewritten"], candidates, top_n=15, use_llm=use_llm)

    # Stage 4
    final_chunks = await apply_user_signals(
        user_id=user_id,
        query_embedding=query_data["embedding"],
        chunks=reranked,
        db=db,
        top_n=8,
    )

    # Context assembly
    prompt = _build_prompt(query_data["rewritten"], final_chunks, conversation_history)

    return final_chunks, prompt


def _build_prompt(query: str, chunks: list[dict], history: list[dict]) -> list[dict]:
    """Build the messages array for the Anthropic API."""
    sources = "\n\n".join(
        f"[Source {i+1}] {c['content']}" for i, c in enumerate(chunks)
    )
    messages = []

    for m in history[-10:]:
        messages.append({"role": m["role"], "content": m["content"]})

    messages.append({
        "role": "user",
        "content": f"Sources:\n{sources}\n\nQuestion: {query}",
    })

    return messages


async def stream_response(prompt_messages: list[dict]):
    """Yield SSE text chunks from Claude Sonnet (streaming)."""
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    async with client.messages.stream(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=prompt_messages,
    ) as stream:
        async for text in stream.text_stream:
            yield text
