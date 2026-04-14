from uuid import UUID
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import get_current_user
from app.database import get_db

router = APIRouter(prefix="/api/folders", tags=["folders"])


class CreateFolderRequest(BaseModel):
    name: str
    color: str = "#D4A853"
    icon: str = "📁"


@router.post("")
async def create_folder(body: CreateFolderRequest, user=Depends(get_current_user), db=Depends(get_db)):
    """Create a new folder."""
    # TODO: implement
    pass


@router.get("")
async def list_folders(user=Depends(get_current_user), db=Depends(get_db)):
    """List user's folders with document counts."""
    # TODO: implement
    pass


@router.put("/{folder_id}")
async def update_folder(folder_id: UUID, body: CreateFolderRequest, user=Depends(get_current_user), db=Depends(get_db)):
    """Rename a folder or update its color/icon."""
    # TODO: implement
    pass


@router.delete("/{folder_id}")
async def delete_folder(folder_id: UUID, user=Depends(get_current_user), db=Depends(get_db)):
    """Delete a folder; documents move to unfiled (folder_id = NULL)."""
    # TODO: implement
    pass


@router.post("/{folder_id}/share")
async def share_folder(folder_id: UUID, user=Depends(get_current_user), db=Depends(get_db)):
    """Grant access to all documents in a folder."""
    # TODO: implement
    pass
