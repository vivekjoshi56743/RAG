from fastapi import APIRouter, Depends
from pydantic import BaseModel
from uuid import UUID

from app.auth import get_current_user
from app.database import get_db

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


class FeedbackPayload(BaseModel):
    query_text: str
    chunk_id: UUID
    document_id: UUID
    signal_type: str   # thumbs_up | thumbs_down | citation_click | copy_text | reformulation
    conversation_id: UUID | None = None
    message_id: UUID | None = None
    metadata: dict = {}


@router.post("")
async def record_feedback(
    payload: FeedbackPayload,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """Store a user feedback signal used to personalize future retrieval."""
    # TODO: implement — insert into user_feedback, refresh materialized view if needed
    pass
