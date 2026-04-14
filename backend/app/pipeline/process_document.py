"""
Async document processing pipeline:
  Parse → Structure Detection → Chunk → Enrich → Embed → Index → Summarize

Runs as a Cloud Run Job triggered after upload.
"""
import asyncio
from uuid import UUID

from app.services.parsers import get_parser
from app.services.chunker import chunk_document
from app.services.embedder import embed_documents, build_embedding_text
from app.services.summarizer import generate_summary
from app.services.storage import download_file


async def process_document(document_id: UUID, gcs_path: str, doc_name: str, db) -> None:
    """Full pipeline: download from GCS → parse → chunk → enrich → embed → store."""
    try:
        await _update_status(document_id, "processing", db)

        # Step 1: Download and parse
        file_bytes = download_file(gcs_path)
        parser = get_parser(doc_name)
        pages = parser.extract(file_bytes)

        # Step 2: Generate document summary (async, runs before embedding)
        full_text = "\n".join(p["text"] for p in pages)
        summary_data = await generate_summary(full_text, doc_name)
        await _store_summary(document_id, summary_data, db)

        # Step 3: Adaptive chunking
        chunks = await chunk_document(
            pages=pages,
            doc_id=document_id,
            doc_name=doc_name,
            summary=summary_data.get("summary", ""),
        )

        # Step 4: Hypothetical question generation (enrichment)
        chunks = await _enrich_with_questions(chunks, doc_name)

        # Step 5: Embed chunk content (contextual prefix)
        chunk_texts = [build_embedding_text(c) for c in chunks]
        content_embeddings = await embed_documents(chunk_texts)

        # Step 6: Embed hypothetical questions
        question_texts = [
            " ".join(c.get("hypothetical_questions", [])) or c["content"][:500]
            for c in chunks
        ]
        question_embeddings = await embed_documents(question_texts)

        # Step 7: Insert all chunks into the DB
        await _store_chunks(document_id, chunks, content_embeddings, question_embeddings, db)

        await _update_status(document_id, "indexed", db)

    except Exception as exc:
        await _update_status(document_id, "error", db, error_message=str(exc))
        raise


async def _enrich_with_questions(chunks: list[dict], doc_name: str) -> list[dict]:
    """Generate 2 hypothetical questions per chunk via Claude (batched)."""
    from app.services.embedder import embed_documents  # noqa: re-import for clarity
    import anthropic
    from app.config import settings

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def gen_questions(chunk: dict) -> list[str]:
        heading = chunk.get("section_heading", "")
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": (
                    f"Given this text from '{doc_name}' ({heading}):\n"
                    f"{chunk['content'][:1500]}\n\n"
                    "Write exactly 2 specific questions this text answers. One per line, no bullets."
                ),
            }],
        )
        return [q.strip() for q in response.content[0].text.strip().split("\n") if q.strip()][:2]

    tasks = [gen_questions(c) for c in chunks]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for chunk, result in zip(chunks, results):
        if isinstance(result, list):
            chunk["hypothetical_questions"] = result

    return chunks


async def _update_status(doc_id: UUID, status: str, db, error_message: str | None = None) -> None:
    # TODO: UPDATE documents SET status = :status WHERE id = :id
    pass


async def _store_summary(doc_id: UUID, summary_data: dict, db) -> None:
    # TODO: UPDATE documents SET summary = :s, key_topics = :t, document_type = :dt WHERE id = :id
    pass


async def _store_chunks(
    doc_id: UUID,
    chunks: list[dict],
    content_embeddings: list[list[float]],
    question_embeddings: list[list[float]],
    db,
) -> None:
    # TODO: bulk INSERT into chunks table
    pass
