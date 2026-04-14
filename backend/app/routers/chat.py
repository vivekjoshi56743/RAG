from uuid import UUID
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.auth import get_current_user
from app.database import get_db

router = APIRouter(prefix="/api/conversations", tags=["chat"])


@router.post("")
async def create_conversation(user=Depends(get_current_user), db=Depends(get_db)):
    """Create a new conversation."""
    # TODO: implement
    pass


@router.get("")
async def list_conversations(user=Depends(get_current_user), db=Depends(get_db)):
    """List user's conversations."""
    # TODO: implement
    pass


@router.get("/{conv_id}")
async def get_conversation(conv_id: UUID, user=Depends(get_current_user), db=Depends(get_db)):
    """Get conversation with all messages."""
    # TODO: implement
    pass


@router.post("/{conv_id}/messages")
async def send_message(conv_id: UUID, user=Depends(get_current_user), db=Depends(get_db)):
    """Send a message and get a streamed RAG response via SSE."""
    # TODO: implement 4-stage RAG pipeline + streaming
    pass


@router.delete("/{conv_id}")
async def delete_conversation(conv_id: UUID, user=Depends(get_current_user), db=Depends(get_db)):
    """Delete a conversation and all its messages."""
    # TODO: implement
    pass


@router.post("/{conv_id}/share")
async def share_conversation(conv_id: UUID, user=Depends(get_current_user), db=Depends(get_db)):
    """Create a shareable public snapshot of this conversation."""
    # TODO: implement
    pass
