import json
import re
import secrets
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.auth import get_current_user
from app.database import get_db, AsyncSessionLocal
from app.services.conversation_titler import maybe_autotitle_conversation
from app.services.rag import run_rag_pipeline, stream_response
from app.services.user_context import get_or_create_user

router = APIRouter(prefix="/api/conversations", tags=["chat"])


class SendMessageRequest(BaseModel):
    content: str
    document_ids: list[UUID] | None = None
    folder_id: UUID | None = None


class UpdateConversationRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)


def _extract_citations(answer_text: str, chunks: list[dict]) -> list[dict]:
    matches = sorted({int(m) for m in re.findall(r"\[Source\s+(\d+)\]", answer_text)})
    citations = []
    for source_idx in matches:
        if source_idx <= 0 or source_idx > len(chunks):
            continue
        chunk = chunks[source_idx - 1]
        citations.append(
            {
                "source": source_idx,
                "chunk_id": str(chunk["id"]),
                "document_id": str(chunk["document_id"]),
                "doc_name": chunk.get("doc_name"),
                "page": chunk.get("page_number"),
                "snippet": chunk.get("content", "")[:300],
            }
        )
    return citations


async def _persist_assistant_message(conv_id: UUID, content: str, citations: list[dict]) -> None:
    """Persist assistant turn using a dedicated DB session (safe for streaming tail)."""
    async with AsyncSessionLocal() as write_db:
        await write_db.execute(
            text(
                """
                INSERT INTO messages (conversation_id, role, content, citations)
                VALUES (:conv_id, 'assistant', :content, CAST(:citations AS jsonb))
                """
            ),
            {
                "conv_id": str(conv_id),
                "content": content,
                "citations": json.dumps(citations),
            },
        )
        await write_db.execute(
            text("UPDATE conversations SET updated_at = now() WHERE id = :id"),
            {"id": str(conv_id)},
        )
        await write_db.commit()


@router.post("")
async def create_conversation(user=Depends(get_current_user), db=Depends(get_db)):
    """Create a new conversation."""
    user_row = await get_or_create_user(db, user)
    row = (
        await db.execute(
            text(
                """
                INSERT INTO conversations (user_id, title)
                VALUES (:uid, 'New Chat')
                RETURNING id, user_id, title, created_at, updated_at
                """
            ),
            {"uid": str(user_row["id"])},
        )
    ).mappings().first()
    await db.commit()
    return dict(row)


@router.get("")
async def list_conversations(
    q: str | None = Query(None),
    user=Depends(get_current_user), db=Depends(get_db)
):
    """List user's conversations."""
    user_row = await get_or_create_user(db, user)

    if q:
        q_pattern = f"%{q}%"
        query_sql = text(
            """
            SELECT
                c.id,
                c.title,
                c.created_at,
                c.updated_at,
                COALESCE(
                    (SELECT m.content FROM messages m WHERE m.conversation_id = c.id AND m.content ILIKE :q_pattern ORDER BY m.created_at DESC LIMIT 1),
                    (SELECT m.content FROM messages m WHERE m.conversation_id = c.id ORDER BY m.created_at DESC LIMIT 1)
                ) AS last_message,
                lm_time.last_message_at
            FROM conversations c
            LEFT JOIN LATERAL (
                SELECT m.created_at AS last_message_at
                FROM messages m
                WHERE m.conversation_id = c.id
                ORDER BY m.created_at DESC
                LIMIT 1
            ) lm_time ON TRUE
            WHERE c.user_id = :uid
            AND (
                c.title ILIKE :q_pattern
                OR EXISTS (
                    SELECT 1 FROM messages m WHERE m.conversation_id = c.id AND m.content ILIKE :q_pattern
                )
            )
            ORDER BY c.updated_at DESC
            """
        )
        params = {"uid": str(user_row["id"]), "q_pattern": q_pattern}
    else:
        query_sql = text(
            """
            SELECT
                c.id,
                c.title,
                c.created_at,
                c.updated_at,
                lm.content AS last_message,
                lm.created_at AS last_message_at
            FROM conversations c
            LEFT JOIN LATERAL (
                SELECT m.content, m.created_at
                FROM messages m
                WHERE m.conversation_id = c.id
                ORDER BY m.created_at DESC
                LIMIT 1
            ) lm ON TRUE
            WHERE c.user_id = :uid
            ORDER BY c.updated_at DESC
            """
        )
        params = {"uid": str(user_row["id"])}

    rows = (await db.execute(query_sql, params)).mappings().all()
    return [dict(r) for r in rows]


@router.get("/{conv_id}")
async def get_conversation(conv_id: UUID, user=Depends(get_current_user), db=Depends(get_db)):
    """Get conversation with all messages."""
    user_row = await get_or_create_user(db, user)
    conv = (
        await db.execute(
            text("SELECT * FROM conversations WHERE id = :id AND user_id = :uid"),
            {"id": str(conv_id), "uid": str(user_row["id"])},
        )
    ).mappings().first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = (
        await db.execute(
            text(
                """
                SELECT id, role, content, citations, created_at
                FROM messages
                WHERE conversation_id = :id
                ORDER BY created_at ASC
                """
            ),
            {"id": str(conv_id)},
        )
    ).mappings().all()
    return {**dict(conv), "messages": [dict(m) for m in messages]}


@router.post("/{conv_id}/messages")
async def send_message(
    conv_id: UUID,
    body: SendMessageRequest,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """Send a message and get a streamed RAG response via SSE."""
    user_row = await get_or_create_user(db, user)
    conv = (
        await db.execute(
            text("SELECT * FROM conversations WHERE id = :id AND user_id = :uid"),
            {"id": str(conv_id), "uid": str(user_row["id"])},
        )
    ).mappings().first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if not body.content.strip():
        raise HTTPException(status_code=400, detail="Message content cannot be empty")

    await db.execute(
        text(
            """
            INSERT INTO messages (conversation_id, role, content, citations)
            VALUES (:conv_id, 'user', :content, '[]'::jsonb)
            """
        ),
        {"conv_id": str(conv_id), "content": body.content},
    )
    await db.execute(
        text("UPDATE conversations SET updated_at = now() WHERE id = :id"),
        {"id": str(conv_id)},
    )
    await db.commit()

    history_rows = (
        await db.execute(
            text(
                """
                SELECT role, content
                FROM messages
                WHERE conversation_id = :id
                ORDER BY created_at ASC
                """
            ),
            {"id": str(conv_id)},
        )
    ).mappings().all()
    history = [dict(m) for m in history_rows]

    selected_docs = body.document_ids if body.document_ids else None
    final_chunks, prompt_messages, is_enumeration = await run_rag_pipeline(
        user_id=user_row["id"],
        query=body.content,
        conversation_history=history,
        db=db,
        document_ids=selected_docs,
        folder_id=body.folder_id,
    )

    # Decide *before* streaming whether this is the first exchange so we can
    # auto-title afterwards. At this point the user message is already persisted,
    # so "first exchange" means: exactly one user message and no assistant messages.
    is_first_exchange = (
        sum(1 for m in history if m["role"] == "user") == 1
        and not any(m["role"] == "assistant" for m in history)
        and (conv["title"] or "").strip() == "New Chat"
    )
    first_user_msg = body.content

    async def event_stream():
        full_answer = ""
        try:
            async for token in stream_response(prompt_messages, is_enumeration=is_enumeration):
                full_answer += token
                payload = {"type": "token", "text": token}
                yield f"data: {json.dumps(payload)}\n\n"

            citations = _extract_citations(full_answer, final_chunks)
            await _persist_assistant_message(conv_id, full_answer, citations)

            done_payload: dict = {"type": "done", "citations": citations}

            # Best-effort auto-title the conversation if this was the first exchange.
            # Await inline (small LLM call ~30 tokens) so the frontend receives the
            # new title in the 'done' event and doesn't need to refetch.
            if is_first_exchange:
                new_title = await maybe_autotitle_conversation(
                    conv_id, user_row["id"], first_user_msg, full_answer
                )
                if new_title:
                    done_payload["title"] = new_title

            yield f"data: {json.dumps(done_payload)}\n\n"
        except Exception as exc:
            error_text = "Sorry, I ran into an error while generating the response."
            try:
                await _persist_assistant_message(conv_id, error_text, [])
            except Exception:
                # Do not mask the original stream failure if persistence also fails.
                pass
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.patch("/{conv_id}")
async def update_conversation(
    conv_id: UUID,
    body: UpdateConversationRequest,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """Rename a conversation."""
    user_row = await get_or_create_user(db, user)
    new_title = body.title.strip()
    if not new_title:
        raise HTTPException(status_code=400, detail="Title cannot be empty")

    row = (
        await db.execute(
            text(
                """
                UPDATE conversations
                SET title = :title, updated_at = now()
                WHERE id = :id AND user_id = :uid
                RETURNING id, user_id, title, created_at, updated_at
                """
            ),
            {"id": str(conv_id), "uid": str(user_row["id"]), "title": new_title[:120]},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await db.commit()
    return dict(row)


@router.delete("/{conv_id}")
async def delete_conversation(conv_id: UUID, user=Depends(get_current_user), db=Depends(get_db)):
    """Delete a conversation and all its messages."""
    user_row = await get_or_create_user(db, user)
    await db.execute(
        text("DELETE FROM conversations WHERE id = :id AND user_id = :uid"),
        {"id": str(conv_id), "uid": str(user_row["id"])},
    )
    await db.commit()
    return {"deleted": True}


@router.post("/{conv_id}/share")
async def share_conversation(conv_id: UUID, user=Depends(get_current_user), db=Depends(get_db)):
    """Create a shareable public snapshot of this conversation."""
    user_row = await get_or_create_user(db, user)
    conv = (
        await db.execute(
            text("SELECT id, title FROM conversations WHERE id = :id AND user_id = :uid"),
            {"id": str(conv_id), "uid": str(user_row["id"])},
        )
    ).mappings().first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = (
        await db.execute(
            text(
                """
                SELECT role, content, citations, created_at
                FROM messages
                WHERE conversation_id = :id
                ORDER BY created_at ASC
                """
            ),
            {"id": str(conv_id)},
        )
    ).mappings().all()
    snapshot = {
        "messages": [dict(m) for m in messages],
        "created_at": datetime.utcnow().isoformat(),
    }
    token = secrets.token_urlsafe(8)[:10]
    await db.execute(
        text(
            """
            INSERT INTO shared_threads (conversation_id, owner_id, share_token, title, snapshot)
            VALUES (:conv_id, :owner_id, :token, :title, CAST(:snapshot AS jsonb))
            """
        ),
        {
            "conv_id": str(conv_id),
            "owner_id": str(user_row["id"]),
            "token": token,
            "title": conv["title"],
            "snapshot": json.dumps(jsonable_encoder(snapshot)),
        },
    )
    await db.commit()
    return {"share_token": token}
