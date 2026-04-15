from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from app.auth import get_current_user
from app.database import get_db
from app.services.access import user_has_folder_access
from app.services.user_context import get_or_create_user

router = APIRouter(prefix="/api/folders", tags=["folders"])


class CreateFolderRequest(BaseModel):
    name: str
    color: str = "#D4A853"
    icon: str = "📁"


class ShareFolderRequest(BaseModel):
    email: str
    role: str = "viewer"  # viewer | editor | admin


@router.post("")
async def create_folder(body: CreateFolderRequest, user=Depends(get_current_user), db=Depends(get_db)):
    """Create a new folder."""
    user_row = await get_or_create_user(db, user)
    row = (
        await db.execute(
            text(
                """
                INSERT INTO folders (user_id, name, color, icon)
                VALUES (:uid, :name, :color, :icon)
                RETURNING *
                """
            ),
            {
                "uid": str(user_row["id"]),
                "name": body.name,
                "color": body.color,
                "icon": body.icon,
            },
        )
    ).mappings().first()
    await db.commit()
    return dict(row)


@router.get("")
async def list_folders(user=Depends(get_current_user), db=Depends(get_db)):
    """List user's folders with document counts."""
    user_row = await get_or_create_user(db, user)
    rows = (
        await db.execute(
            text(
                """
                SELECT f.*, COUNT(d.id) AS doc_count
                FROM folders f
                LEFT JOIN documents d ON d.folder_id = f.id
                WHERE f.user_id = :uid
                GROUP BY f.id
                ORDER BY f.sort_order, f.created_at
                """
            ),
            {"uid": str(user_row["id"])},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


@router.put("/{folder_id}")
async def update_folder(folder_id: UUID, body: CreateFolderRequest, user=Depends(get_current_user), db=Depends(get_db)):
    """Rename a folder or update its color/icon."""
    user_row = await get_or_create_user(db, user)
    if not await user_has_folder_access(db, str(user_row["id"]), str(folder_id), min_role="editor"):
        raise HTTPException(status_code=403, detail="Not authorized to update this folder")

    await db.execute(
        text(
            """
            UPDATE folders
            SET name = :name, color = :color, icon = :icon
            WHERE id = :id
            """
        ),
        {"id": str(folder_id), "name": body.name, "color": body.color, "icon": body.icon},
    )
    await db.commit()
    return {"updated": True}


@router.delete("/{folder_id}")
async def delete_folder(folder_id: UUID, user=Depends(get_current_user), db=Depends(get_db)):
    """Delete a folder; documents move to unfiled (folder_id = NULL)."""
    user_row = await get_or_create_user(db, user)
    if not await user_has_folder_access(db, str(user_row["id"]), str(folder_id), min_role="admin"):
        raise HTTPException(status_code=403, detail="Not authorized to delete this folder")

    await db.execute(
        text("UPDATE documents SET folder_id = NULL WHERE folder_id = :folder_id"),
        {"folder_id": str(folder_id)},
    )
    await db.execute(text("DELETE FROM folders WHERE id = :id"), {"id": str(folder_id)})
    await db.commit()
    return {"deleted": True}


@router.post("/{folder_id}/share")
async def share_folder(
    folder_id: UUID,
    body: ShareFolderRequest,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """Grant access to all documents in a folder."""
    user_row = await get_or_create_user(db, user)
    if body.role not in {"viewer", "editor", "admin"}:
        raise HTTPException(status_code=400, detail="Invalid role")
    if not await user_has_folder_access(db, str(user_row["id"]), str(folder_id), min_role="admin"):
        raise HTTPException(status_code=403, detail="Not authorized to share this folder")

    grantee = (
        await db.execute(
            text("SELECT id FROM users WHERE email = :email"),
            {"email": body.email},
        )
    ).mappings().first()
    if not grantee:
        raise HTTPException(status_code=404, detail="User not found")

    await db.execute(
        text(
            """
            INSERT INTO permissions (folder_id, grantor_id, grantee_id, role)
            VALUES (:folder_id, :grantor_id, :grantee_id, :role)
            ON CONFLICT (folder_id, grantee_id) DO UPDATE SET role = EXCLUDED.role
            """
        ),
        {
            "folder_id": str(folder_id),
            "grantor_id": str(user_row["id"]),
            "grantee_id": str(grantee["id"]),
            "role": body.role,
        },
    )
    await db.commit()
    return {"shared": True}
