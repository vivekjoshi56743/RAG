from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from app.auth import get_current_user
from app.database import get_db
from app.services.access import user_has_document_access
from app.services.user_context import get_or_create_user

router = APIRouter(prefix="/api", tags=["permissions"])


class ShareRequest(BaseModel):
    email: str
    role: str = "viewer"  # viewer | editor | admin


@router.post("/documents/{doc_id}/share")
async def share_document(doc_id: UUID, body: ShareRequest, user=Depends(get_current_user), db=Depends(get_db)):
    """Grant another user access to a document."""
    user_row = await get_or_create_user(db, user)
    if body.role not in {"viewer", "editor", "admin"}:
        raise HTTPException(status_code=400, detail="Invalid role")
    if not await user_has_document_access(db, str(user_row["id"]), str(doc_id), min_role="admin"):
        raise HTTPException(status_code=403, detail="Not authorized to share this document")

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
            INSERT INTO permissions (document_id, grantor_id, grantee_id, role)
            VALUES (:doc_id, :grantor_id, :grantee_id, :role)
            ON CONFLICT (document_id, grantee_id) DO UPDATE SET role = EXCLUDED.role
            """
        ),
        {
            "doc_id": str(doc_id),
            "grantor_id": str(user_row["id"]),
            "grantee_id": str(grantee["id"]),
            "role": body.role,
        },
    )
    await db.commit()
    return {"shared": True}


@router.get("/documents/{doc_id}/permissions")
async def list_permissions(doc_id: UUID, user=Depends(get_current_user), db=Depends(get_db)):
    """List all users who have access to this document."""
    user_row = await get_or_create_user(db, user)
    if not await user_has_document_access(db, str(user_row["id"]), str(doc_id), min_role="admin"):
        raise HTTPException(status_code=403, detail="Not authorized to view permissions")

    rows = (
        await db.execute(
            text(
                """
                SELECT p.id, p.role, p.created_at, u.id AS user_id, u.email, u.display_name
                FROM permissions p
                JOIN users u ON u.id = p.grantee_id
                WHERE p.document_id = :doc_id
                ORDER BY p.created_at DESC
                """
            ),
            {"doc_id": str(doc_id)},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


@router.delete("/documents/{doc_id}/permissions/{perm_id}")
async def revoke_permission(doc_id: UUID, perm_id: UUID, user=Depends(get_current_user), db=Depends(get_db)):
    """Revoke a user's access to a document."""
    user_row = await get_or_create_user(db, user)
    if not await user_has_document_access(db, str(user_row["id"]), str(doc_id), min_role="admin"):
        raise HTTPException(status_code=403, detail="Not authorized to revoke permissions")

    await db.execute(
        text("DELETE FROM permissions WHERE id = :perm_id AND document_id = :doc_id"),
        {"perm_id": str(perm_id), "doc_id": str(doc_id)},
    )
    await db.commit()
    return {"revoked": True}
