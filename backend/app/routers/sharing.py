import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from app.auth import get_current_user
from app.database import get_db
from app.services.user_context import get_or_create_user

router = APIRouter(prefix="/api/shared", tags=["sharing"])


@router.get("/{token}")
async def get_shared_thread(token: str, db=Depends(get_db)):
    """Public endpoint — no auth required. Returns a read-only frozen conversation snapshot."""
    row = (
        await db.execute(
            text(
                """
                UPDATE shared_threads
                SET view_count = view_count + 1
                WHERE share_token = :token
                  AND is_active = true
                  AND (expires_at IS NULL OR expires_at > now())
                RETURNING title, snapshot, view_count, created_at
                """
            ),
            {"token": token},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Thread not found or revoked")

    snapshot = row["snapshot"]
    if isinstance(snapshot, str):
        snapshot = json.loads(snapshot)
    return {
        "title": row["title"],
        "messages": snapshot.get("messages", []),
        "view_count": row["view_count"],
        "shared_at": row["created_at"],
    }


@router.delete("/{token}")
async def revoke_share(token: str, user=Depends(get_current_user), db=Depends(get_db)):
    """Owner revokes a shared conversation link."""
    user_row = await get_or_create_user(db, user)
    result = await db.execute(
        text(
            """
            UPDATE shared_threads
            SET is_active = false
            WHERE share_token = :token AND owner_id = :owner_id
            """
        ),
        {"token": token, "owner_id": str(user_row["id"])},
    )
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Share token not found")
    return {"revoked": True}
