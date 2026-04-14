from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user
from app.database import get_db

router = APIRouter(prefix="/api/shared", tags=["sharing"])


@router.get("/{token}")
async def get_shared_thread(token: str, db=Depends(get_db)):
    """Public endpoint — no auth required. Returns a read-only frozen conversation snapshot."""
    # TODO: implement — fetch shared_threads by token, increment view_count
    pass


@router.delete("/{token}")
async def revoke_share(token: str, user=Depends(get_current_user), db=Depends(get_db)):
    """Owner revokes a shared conversation link."""
    # TODO: implement
    pass
