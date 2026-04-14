from uuid import UUID
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, BackgroundTasks

from app.auth import get_current_user
from app.database import get_db

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """Accept file, store in GCS, create DB record, trigger pipeline."""
    # TODO: implement
    pass


@router.get("")
async def list_documents(user=Depends(get_current_user), db=Depends(get_db)):
    """List user's documents with status."""
    # TODO: implement
    pass


@router.get("/{doc_id}")
async def get_document(doc_id: UUID, user=Depends(get_current_user), db=Depends(get_db)):
    """Get single document details."""
    # TODO: implement
    pass


@router.delete("/{doc_id}")
async def delete_document(doc_id: UUID, user=Depends(get_current_user), db=Depends(get_db)):
    """Delete document, chunks, and GCS file."""
    # TODO: implement
    pass


@router.put("/{doc_id}/move")
async def move_document(doc_id: UUID, user=Depends(get_current_user), db=Depends(get_db)):
    """Move document into a folder."""
    # TODO: implement
    pass


@router.put("/bulk-move")
async def bulk_move_documents(user=Depends(get_current_user), db=Depends(get_db)):
    """Move multiple documents into a folder."""
    # TODO: implement
    pass
