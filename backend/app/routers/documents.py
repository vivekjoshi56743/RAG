import asyncio
import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from app.auth import get_current_user
from app.database import get_db, AsyncSessionLocal
from app.pipeline.process_document import process_document
from app.services.access import user_has_document_access, user_has_folder_access
from app.services.storage import delete_file, upload_file
from app.services.user_context import get_or_create_user

router = APIRouter(prefix="/api/documents", tags=["documents"])


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


class MoveRequest(BaseModel):
    folder_id: UUID | None = None


class BulkMoveRequest(BaseModel):
    document_ids: list[UUID]
    folder_id: UUID | None = None


def _extension(filename: str) -> str:
    if "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[-1].lower()


async def _run_pipeline(doc_id: UUID, gcs_path: str, doc_name: str) -> None:
    async with AsyncSessionLocal() as session:
        await process_document(doc_id, gcs_path, doc_name, session)


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """Accept file, store in GCS, create DB record, trigger pipeline."""
    ext = _extension(file.filename or "")
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext or 'unknown'}")

    user_row = await get_or_create_user(db, user)
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    destination = f"{user_row['id']}/{uuid.uuid4()}-{file.filename}"
    gcs_path = upload_file(
        file_bytes=file_bytes,
        destination_path=destination,
        content_type=file.content_type or "application/octet-stream",
    )

    inserted = (
        await db.execute(
            text(
                """
                INSERT INTO documents (
                    id, user_id, name, file_path, file_size, mime_type, status
                ) VALUES (
                    :id, :uid, :name, :file_path, :file_size, :mime_type, 'uploaded'
                )
                RETURNING id, user_id, name, file_path, file_size, mime_type, status, created_at
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "uid": user_row["id"],
                "name": file.filename,
                "file_path": gcs_path,
                "file_size": len(file_bytes),
                "mime_type": file.content_type,
            },
        )
    ).mappings().first()
    await db.commit()
    asyncio.create_task(_run_pipeline(inserted["id"], gcs_path, file.filename or "document"))
    return dict(inserted)


@router.get("")
async def list_documents(user=Depends(get_current_user), db=Depends(get_db)):
    """List user's documents with status."""
    user_row = await get_or_create_user(db, user)
    rows = (
        await db.execute(
            text(
                """
                SELECT DISTINCT
                    d.*,
                    CASE
                        WHEN d.user_id = :uid THEN 'owner'
                        ELSE COALESCE(p_doc.role, p_folder.role, 'viewer')
                    END AS user_role
                FROM documents d
                LEFT JOIN permissions p_doc
                    ON p_doc.document_id = d.id AND p_doc.grantee_id = :uid
                LEFT JOIN permissions p_folder
                    ON p_folder.folder_id = d.folder_id AND p_folder.grantee_id = :uid
                WHERE d.user_id = :uid
                    OR p_doc.grantee_id = :uid
                    OR p_folder.grantee_id = :uid
                ORDER BY d.updated_at DESC NULLS LAST, d.created_at DESC
                """
            ),
            {"uid": user_row["id"]},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


@router.get("/{doc_id}")
async def get_document(doc_id: UUID, user=Depends(get_current_user), db=Depends(get_db)):
    """Get single document details."""
    user_row = await get_or_create_user(db, user)
    if not await user_has_document_access(db, str(user_row["id"]), str(doc_id), min_role="viewer"):
        raise HTTPException(status_code=404, detail="Document not found")

    row = (
        await db.execute(
            text("SELECT * FROM documents WHERE id = :id"),
            {"id": str(doc_id)},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
        
    doc = dict(row)
    if doc.get("file_path"):
        from app.services.storage import generate_signed_url
        try:
            doc["signed_url"] = generate_signed_url(doc["file_path"])
        except Exception as e:
            doc["signed_url"] = None
    return doc


@router.delete("/{doc_id}")
async def delete_document(doc_id: UUID, user=Depends(get_current_user), db=Depends(get_db)):
    """Delete document, chunks, and GCS file."""
    user_row = await get_or_create_user(db, user)
    can_delete = await user_has_document_access(db, str(user_row["id"]), str(doc_id), min_role="admin")
    if not can_delete:
        raise HTTPException(status_code=403, detail="Not authorized to delete this document")

    row = (
        await db.execute(
            text("SELECT file_path FROM documents WHERE id = :id"),
            {"id": str(doc_id)},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")

    await db.execute(text("DELETE FROM documents WHERE id = :id"), {"id": str(doc_id)})
    await db.commit()
    try:
        delete_file(row["file_path"])
    except Exception:
        # Keep DB deletion durable even if object storage cleanup fails.
        pass
    return {"deleted": True}


@router.put("/{doc_id}/move")
async def move_document(
    doc_id: UUID,
    body: MoveRequest,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """Move document into a folder."""
    user_row = await get_or_create_user(db, user)
    if not await user_has_document_access(db, str(user_row["id"]), str(doc_id), min_role="editor"):
        raise HTTPException(status_code=403, detail="Not authorized to move this document")

    if body.folder_id and not await user_has_folder_access(
        db, str(user_row["id"]), str(body.folder_id), min_role="editor"
    ):
        raise HTTPException(status_code=403, detail="Not authorized to use target folder")

    await db.execute(
        text(
            """
            UPDATE documents
            SET folder_id = :folder_id, updated_at = now()
            WHERE id = :doc_id
            """
        ),
        {"folder_id": str(body.folder_id) if body.folder_id else None, "doc_id": str(doc_id)},
    )
    await db.commit()
    return {"moved": True}


@router.put("/bulk-move")
async def bulk_move_documents(
    body: BulkMoveRequest,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """Move multiple documents into a folder."""
    user_row = await get_or_create_user(db, user)
    if not body.document_ids:
        return {"moved": 0}

    if body.folder_id and not await user_has_folder_access(
        db, str(user_row["id"]), str(body.folder_id), min_role="editor"
    ):
        raise HTTPException(status_code=403, detail="Not authorized to use target folder")

    for doc_id in body.document_ids:
        if not await user_has_document_access(db, str(user_row["id"]), str(doc_id), min_role="editor"):
            raise HTTPException(status_code=403, detail=f"Not authorized to move document {doc_id}")

    await db.execute(
        text(
            """
            UPDATE documents
            SET folder_id = :folder_id, updated_at = now()
            WHERE id = ANY(:doc_ids)
            """
        ),
        {
            "folder_id": str(body.folder_id) if body.folder_id else None,
            "doc_ids": [str(doc_id) for doc_id in body.document_ids],
        },
    )
    await db.commit()
    return {"moved": len(body.document_ids)}
