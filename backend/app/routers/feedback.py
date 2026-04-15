from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from uuid import UUID
from sqlalchemy import text

from app.auth import get_current_user
from app.database import get_db
from app.services.embedder import embed_query
from app.services.user_context import get_or_create_user

router = APIRouter(prefix="/api/feedback", tags=["feedback"])

SIGNAL_WEIGHTS = {
    "thumbs_up": 3.0,
    "thumbs_down": -3.0,
    "citation_click": 2.0,
    "copy_text": 1.0,
    "search_result_click": 2.0,
    "search_result_skip": -0.5,
    "reformulation": -1.0,
    "follow_up_question": 1.0,
}


class FeedbackPayload(BaseModel):
    query_text: str
    chunk_id: UUID
    document_id: UUID
    signal_type: str   # thumbs_up | thumbs_down | citation_click | copy_text | reformulation
    conversation_id: UUID | None = None
    message_id: UUID | None = None
    metadata: dict = Field(default_factory=dict)


@router.post("")
async def record_feedback(
    payload: FeedbackPayload,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """Store a user feedback signal used to personalize future retrieval."""
    signal_weight = SIGNAL_WEIGHTS.get(payload.signal_type)
    if signal_weight is None:
        return {
            "stored": False,
            "reason": f"Unsupported signal_type: {payload.signal_type}",
        }

    user_row = await get_or_create_user(db, user)
    query_vec = await embed_query(payload.query_text)
    query_vec_literal = "[" + ",".join(f"{float(v):.8f}" for v in query_vec) + "]"

    await db.execute(
        text(
            """
            INSERT INTO user_feedback (
                user_id,
                query_text,
                query_embedding,
                chunk_id,
                document_id,
                signal_type,
                signal_weight,
                conversation_id,
                message_id,
                metadata
            ) VALUES (
                :user_id,
                :query_text,
                CAST(:query_embedding AS vector),
                :chunk_id,
                :document_id,
                :signal_type,
                :signal_weight,
                :conversation_id,
                :message_id,
                :metadata
            )
            """
        ),
        {
            "user_id": str(user_row["id"]),
            "query_text": payload.query_text,
            "query_embedding": query_vec_literal,
            "chunk_id": str(payload.chunk_id),
            "document_id": str(payload.document_id),
            "signal_type": payload.signal_type,
            "signal_weight": signal_weight,
            "conversation_id": str(payload.conversation_id) if payload.conversation_id else None,
            "message_id": str(payload.message_id) if payload.message_id else None,
            "metadata": payload.metadata,
        },
    )
    await db.commit()
    return {"stored": True, "signal_weight": signal_weight}
