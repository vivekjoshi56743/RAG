import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_or_create_user(db: AsyncSession, auth_payload: dict) -> dict:
    """
    Resolve auth payload to an internal users row.

    Returns a dict with at least: id, firebase_uid, email, display_name.
    """
    firebase_uid = auth_payload.get("uid")
    if not firebase_uid:
        raise ValueError("Auth payload is missing uid")

    email = auth_payload.get("email") or f"{firebase_uid}@unknown.local"
    display_name = auth_payload.get("name")
    try:
        row = (
            await db.execute(
                text(
                    """
                    INSERT INTO users (id, firebase_uid, email, display_name)
                    VALUES (:id, :firebase_uid, :email, :display_name)
                    ON CONFLICT (firebase_uid) DO UPDATE
                    SET
                        email = EXCLUDED.email,
                        display_name = COALESCE(EXCLUDED.display_name, users.display_name)
                    RETURNING id, firebase_uid, email, display_name
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "firebase_uid": firebase_uid,
                    "email": email,
                    "display_name": display_name,
                },
            )
        ).mappings().first()
        await db.commit()
        return dict(row)
    except Exception:
        await db.rollback()
        raise
