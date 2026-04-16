import asyncio
from uuid import UUID
from app.database import AsyncSessionLocal
from sqlalchemy import text
from fastapi.encoders import jsonable_encoder
import json
import secrets
from datetime import datetime

async def test():
    async with AsyncSessionLocal() as db:
        # Get any conversation
        conv = (await db.execute(text("SELECT id, title, user_id FROM conversations LIMIT 1"))).mappings().first()
        if not conv:
            print("No conversations found.")
            return

        conv_id = conv["id"]
        print(f"Testing conv_id: {conv_id}")

        messages = (await db.execute(
            text("SELECT role, content, citations, created_at FROM messages WHERE conversation_id = :id ORDER BY created_at ASC"),
            {"id": str(conv_id)}
        )).mappings().all()
        
        snapshot = {
            "messages": [dict(m) for m in messages],
            "created_at": datetime.utcnow().isoformat(),
        }
        
        try:
            encoded = jsonable_encoder(snapshot)
            json_str = json.dumps(encoded)
            print("JSON Encoding successful!")
        except Exception as e:
            print(f"JSON Encoding failed: {e}")
            return
            
        token = secrets.token_urlsafe(8)[:10]
        
        try:
            await db.execute(
                text("""
                INSERT INTO shared_threads (conversation_id, owner_id, share_token, title, snapshot)
                VALUES (:conv_id, :owner_id, :token, :title, :snapshot::jsonb)
                """),
                {
                    "conv_id": str(conv_id),
                    "owner_id": str(conv["user_id"]),
                    "token": token,
                    "title": conv["title"],
                    "snapshot": json_str,
                }
            )
            print("DB Insert successful!")
            # rollback to not pollute DB
            await db.rollback()
        except Exception as e:
            print(f"DB Insert failed: {e}")

asyncio.run(test())
