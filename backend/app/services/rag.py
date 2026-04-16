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
from app.services.llm_provider import stream_chat

SYSTEM_PROMPT = """You are a helpful research assistant with access to a knowledge base.

Answer the user's question using ONLY the provided sources. Do not use outside knowledge.

Length and depth:
- Write comprehensive, well-structured answers. Prefer multiple paragraphs over one-liners.
- Synthesize information *across* sources rather than quoting a single one; compare, contrast, and connect related details when the sources support it.
- When the question is broad or open-ended, organize the response with short markdown headings or bullet lists so the reader can scan it.
- Include concrete details the sources provide: names, dates, numbers, places, direct phrasing where it matters.
- Do not pad with filler or restate the question. Length should come from substance, not from repetition.

Citations:
- Cite sources inline as [Source N] immediately after each claim that uses them.
- A single sentence may cite multiple sources, e.g. "[Source 2][Source 5]".
- If the answer is genuinely not in the sources, say so clearly and stop — do not guess."""

ENUMERATION_SUFFIX = """

IMPORTANT — this question asks you to enumerate ALL items of a type (all characters, all themes, all events, etc.).
- Go through EVERY source block provided and extract every relevant item you find.
- Present them as a structured list; do not stop after the first few.
- After your list, add a brief note: "Note: This list is based on the document sections retrieved. If characters or items appear in other parts of the document, they may not be shown here." """


async def run_rag_pipeline(
    user_id: UUID,
    query: str,
    conversation_history: list[dict],
    db,
    document_ids: list[UUID] | None = None,
    folder_id: UUID | None = None,
) -> tuple[list[dict], list[dict], bool]:
    """
    Returns (chunks, prompt_messages, is_enumeration).
    Call stream_response(prompt_messages, is_enumeration) separately to get the SSE stream.
    """
    # Stage 1
    query_data = await process_query(query, conversation_history)

    # Stage 2
    candidates = await retrieve(
        user_id=user_id,
        query_text=query_data["rewritten"],
        query_embedding=query_data["embedding"],
        db=db,
        document_ids=document_ids,
        folder_id=folder_id,
    )

    is_enumeration = query_data.get("is_enumeration", False)

    # Stage 3 — use LLM reranker for comparison queries (multiple sub-queries)
    use_llm = len(query_data["sub_queries"]) > 1
    # Enumeration queries need a wider candidate set because the answers are
    # spread across many disparate chunks (e.g. every character in a novel).
    stage3_top_n = 60 if is_enumeration else 25
    reranked = await rerank(query_data["rewritten"], candidates, top_n=stage3_top_n, use_llm=use_llm)

    # Stage 4 — for enumeration queries pass a broader set; otherwise keep default.
    stage4_top_n = 35 if is_enumeration else 12
    final_chunks = await apply_user_signals(
        user_id=user_id,
        query_embedding=query_data["embedding"],
        chunks=reranked,
        db=db,
        top_n=stage4_top_n,
    )

    # Context assembly
    prompt = _build_prompt(query_data["rewritten"], final_chunks, conversation_history,
                           is_enumeration=is_enumeration)

    return final_chunks, prompt, is_enumeration


def _format_source_header(index: int, chunk: dict) -> str:
    """Build a human-readable provenance header for a retrieved chunk."""
    parts = [f"Source {index}"]
    doc_name = chunk.get("doc_name")
    if doc_name:
        parts.append(f'"{doc_name}"')
    section = chunk.get("section_heading") or chunk.get("section")
    if section:
        parts.append(str(section))
    page = chunk.get("page_number")
    if page is not None:
        parts.append(f"p. {page}")
    source_type = chunk.get("source_type")
    if source_type and source_type not in ("native", None):
        parts.append(f"[{source_type}]")
    return "[" + " — ".join(parts) + "]"


def _build_prompt(query: str, chunks: list[dict], history: list[dict],
                   is_enumeration: bool = False) -> list[dict]:
    """Build the messages array for the chat LLM."""
    source_blocks = []
    for i, c in enumerate(chunks):
        header = _format_source_header(i + 1, c)
        source_blocks.append(f"{header}\n{c['content']}")
    sources = "\n\n".join(source_blocks)

    question_text = query
    if is_enumeration:
        question_text = (
            f"{query}\n\n"
            "(Please list ALL items you can find across every source block above. "
            "Do not stop after a few — go through all sources and be exhaustive.)"
        )

    messages = []

    for m in history[-10:]:
        messages.append({"role": m["role"], "content": m["content"]})

    messages.append({
        "role": "user",
        "content": f"Sources:\n{sources}\n\nQuestion: {question_text}",
    })

    return messages


async def stream_response(prompt_messages: list[dict], is_enumeration: bool = False):
    """Yield SSE text chunks from provider-routed chat model (with fallback)."""
    system = SYSTEM_PROMPT + (ENUMERATION_SUFFIX if is_enumeration else "")
    # Enumeration answers can be very long (listing 20+ characters with descriptions).
    max_tok = 6000 if is_enumeration else 4096
    async for text in stream_chat(
        prompt_messages,
        system=system,
        max_tokens=max_tok,
        temperature=0.0,
    ):
        yield text
