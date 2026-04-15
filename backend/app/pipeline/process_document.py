"""
Async document processing pipeline:
  Parse → Structure Detection → Chunk → Enrich → Embed → Index → Summarize

Runs as a Cloud Run Job triggered after upload.
"""
import asyncio
from uuid import UUID

from sqlalchemy import text

from app.services.parsers import get_parser
from app.services.chunker import chunk_document
from app.services.embedder import embed_documents, build_embedding_text
from app.services.summarizer import generate_summary
from app.services.storage import download_file


def _document_source_type(pages: list[dict]) -> str:
    """
    Summarize per-page source_type into a single document-level tag:
      - "native"       — all pages extracted natively
      - "ocr"          — all pages OCR'd at normal confidence
      - "ocr_low_conf" — all OCR pages were low confidence
      - "hybrid"       — mix of native + OCR pages
      - None when nothing to summarize

    Pages without a source_type are treated as "native" (the default for
    non-PDF parsers that don't tag their output).
    """
    types = {(p.get("source_type") or "native") for p in pages if p.get("text", "").strip()}
    if not types:
        return "native"
    if types == {"native"}:
        return "native"
    if types == {"ocr"}:
        return "ocr"
    if types == {"ocr_low_conf"}:
        return "ocr_low_conf"
    return "hybrid"


async def process_document(document_id: UUID, gcs_path: str, doc_name: str, db) -> None:
    """Full pipeline: download from GCS → parse → chunk → enrich → embed → store."""
    try:
        await _update_status(document_id, "processing", db)

        # Step 1: Download and parse
        file_bytes = download_file(gcs_path)
        parser = get_parser(doc_name)
        pages = parser.extract(file_bytes)
        doc_source_type = _document_source_type(pages)

        # Step 2: Generate document summary (async, runs before embedding)
        full_text = "\n".join(p["text"] for p in pages)
        summary_data = await generate_summary(full_text, doc_name)
        await _store_summary(document_id, summary_data, db)

        # Step 3: Adaptive chunking
        # Build a richer context string that each chunk prepends to its
        # embedding input. Combines summary + key topics so every chunk is
        # anchored to the document's overall subject matter.
        summary_text = summary_data.get("summary") or ""
        key_topics = summary_data.get("key_topics") or []
        summary_context = summary_text
        if key_topics:
            topics_line = "Key topics: " + ", ".join(str(t) for t in key_topics)
            summary_context = f"{summary_text}\n{topics_line}" if summary_text else topics_line

        chunks = await chunk_document(
            pages=pages,
            doc_id=document_id,
            doc_name=doc_name,
            summary=summary_context,
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
        await _store_chunks(
            document_id,
            chunks,
            content_embeddings,
            question_embeddings,
            db,
            source_type=doc_source_type,
        )

        await _update_status(document_id, "indexed", db)

    except Exception as exc:
        await _update_status(document_id, "error", db, error_message=str(exc))
        raise


async def _enrich_with_questions(chunks: list[dict], doc_name: str) -> list[dict]:
    """Generate 2 hypothetical questions per chunk via provider-routed LLM (batched)."""
    from app.services.llm_provider import complete_text

    async def gen_questions(chunk: dict) -> list[str]:
        heading = chunk.get("section_heading", "")
        prompt = (
            f"Given this text from '{doc_name}' ({heading}):\n"
            f"{chunk['content'][:1500]}\n\n"
            "Write exactly 2 specific questions this text answers. One per line, no bullets."
        )
        text, _provider = await complete_text("enrich", prompt, max_tokens=200, temperature=0.2)
        return [q.strip() for q in text.strip().split("\n") if q.strip()][:2]

    tasks = [gen_questions(c) for c in chunks]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for chunk, result in zip(chunks, results):
        if isinstance(result, list):
            chunk["hypothetical_questions"] = result

    return chunks


async def _update_status(doc_id: UUID, status: str, db, error_message: str | None = None) -> None:
    await db.execute(
        text(
            """
            UPDATE documents
            SET status = :status,
                error_message = :error_message,
                updated_at = now()
            WHERE id = :id
            """
        ),
        {"id": str(doc_id), "status": status, "error_message": error_message},
    )
    await db.commit()


async def _store_summary(doc_id: UUID, summary_data: dict, db) -> None:
    import json as _json

    entities = summary_data.get("entities") or []
    await db.execute(
        text(
            """
            UPDATE documents
            SET summary = :summary,
                key_topics = :key_topics,
                document_type = :document_type,
                subtype = :subtype,
                entities = CAST(:entities AS jsonb),
                updated_at = now()
            WHERE id = :id
            """
        ),
        {
            "id": str(doc_id),
            "summary": summary_data.get("summary"),
            "key_topics": summary_data.get("key_topics", []),
            "document_type": summary_data.get("document_type", "general"),
            "subtype": summary_data.get("subtype"),
            "entities": _json.dumps(entities),
        },
    )
    await db.commit()


async def _store_chunks(
    doc_id: UUID,
    chunks: list[dict],
    content_embeddings: list[list[float]],
    question_embeddings: list[list[float]],
    db,
    source_type: str | None = None,
) -> None:
    if not chunks:
        await db.execute(
            text(
                """
                UPDATE documents
                SET num_pages = 0, num_chunks = 0, updated_at = now()
                WHERE id = :id
                """
            ),
            {"id": str(doc_id)},
        )
        await db.commit()
        return

    doc_row = (
        await db.execute(
            text("SELECT user_id FROM documents WHERE id = :id"),
            {"id": str(doc_id)},
        )
    ).mappings().first()
    if not doc_row:
        raise ValueError(f"Document {doc_id} not found while storing chunks")

    def _vector_literal(values: list[float]) -> str:
        return "[" + ",".join(f"{float(v):.8f}" for v in values) + "]"

    rows = []
    for i, chunk in enumerate(chunks):
        rows.append(
            {
                "document_id": str(doc_id),
                "user_id": doc_row["user_id"],
                "chunk_index": chunk.get("chunk_index", i),
                "content": chunk["content"],
                "page_number": chunk.get("page_number"),
                "token_count": chunk.get("token_count"),
                "section": chunk.get("section"),
                "section_heading": chunk.get("section_heading") or chunk.get("detected_heading"),
                "part": chunk.get("part"),
                "parent_chunk_id": chunk.get("parent_chunk_id"),
                "embedding": _vector_literal(content_embeddings[i]),
                "question_embedding": _vector_literal(question_embeddings[i]),
                "hypothetical_questions": chunk.get("hypothetical_questions", []),
                "source_type": source_type,
            }
        )

    await db.execute(text("DELETE FROM chunks WHERE document_id = :id"), {"id": str(doc_id)})
    await db.execute(
        text(
            """
            INSERT INTO chunks (
                document_id,
                user_id,
                chunk_index,
                content,
                page_number,
                token_count,
                section,
                section_heading,
                part,
                parent_chunk_id,
                embedding,
                question_embedding,
                hypothetical_questions,
                source_type
            ) VALUES (
                :document_id,
                :user_id,
                :chunk_index,
                :content,
                :page_number,
                :token_count,
                :section,
                :section_heading,
                :part,
                :parent_chunk_id,
                CAST(:embedding AS vector),
                CAST(:question_embedding AS vector),
                :hypothetical_questions,
                :source_type
            )
            """
        ),
        rows,
    )
    await db.execute(
        text(
            """
            UPDATE documents
            SET num_chunks = :num_chunks,
                num_pages = :num_pages,
                updated_at = now()
            WHERE id = :id
            """
        ),
        {
            "id": str(doc_id),
            "num_chunks": len(chunks),
            "num_pages": max(1, len({c.get("page_number") for c in chunks if c.get("page_number") is not None})),
        },
    )
    await db.commit()
