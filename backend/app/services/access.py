from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


ROLE_RANK = {"viewer": 1, "editor": 2, "admin": 3}


async def user_has_document_access(
    db: AsyncSession,
    user_id: str,
    document_id: str,
    min_role: str = "viewer",
) -> bool:
    required = ROLE_RANK[min_role]
    row = (
        await db.execute(
            text(
                """
                SELECT
                    d.user_id = :uid AS is_owner,
                    p_doc.role AS doc_role,
                    p_folder.role AS folder_role
                FROM documents d
                LEFT JOIN permissions p_doc
                    ON p_doc.document_id = d.id AND p_doc.grantee_id = :uid
                LEFT JOIN permissions p_folder
                    ON p_folder.folder_id = d.folder_id AND p_folder.grantee_id = :uid
                WHERE d.id = :did
                """
            ),
            {"uid": user_id, "did": document_id},
        )
    ).mappings().first()
    if not row:
        return False
    if row["is_owner"]:
        return True

    doc_rank = ROLE_RANK.get(row["doc_role"], 0)
    folder_rank = ROLE_RANK.get(row["folder_role"], 0)
    return max(doc_rank, folder_rank) >= required


async def user_has_folder_access(
    db: AsyncSession,
    user_id: str,
    folder_id: str,
    min_role: str = "viewer",
) -> bool:
    required = ROLE_RANK[min_role]
    row = (
        await db.execute(
            text(
                """
                SELECT
                    f.user_id = :uid AS is_owner,
                    p.role AS role
                FROM folders f
                LEFT JOIN permissions p
                    ON p.folder_id = f.id AND p.grantee_id = :uid
                WHERE f.id = :fid
                """
            ),
            {"uid": user_id, "fid": folder_id},
        )
    ).mappings().first()
    if not row:
        return False
    if row["is_owner"]:
        return True
    return ROLE_RANK.get(row["role"], 0) >= required
