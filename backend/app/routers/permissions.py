from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import get_current_user
from app.database import get_db

router = APIRouter(prefix="/api", tags=["permissions"])


class ShareRequest(BaseModel):
    email: str
    role: str = "viewer"  # viewer | editor | admin


@router.post("/documents/{doc_id}/share")
async def share_document(doc_id: UUID, body: ShareRequest, user=Depends(get_current_user), db=Depends(get_db)):
    """Grant another user access to a document."""
    # TODO: implement — verify caller is admin, look up grantee, upsert permission
    pass


@router.get("/documents/{doc_id}/permissions")
async def list_permissions(doc_id: UUID, user=Depends(get_current_user), db=Depends(get_db)):
    """List all users who have access to this document."""
    # TODO: implement
    pass


@router.delete("/documents/{doc_id}/permissions/{perm_id}")
async def revoke_permission(doc_id: UUID, perm_id: UUID, user=Depends(get_current_user), db=Depends(get_db)):
    """Revoke a user's access to a document."""
    # TODO: implement
    pass
