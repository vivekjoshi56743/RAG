"""
Seed a demo user, folders, and a few sample documents in the database.
Used for local development and demos.

Usage:
    DATABASE_URL=postgresql://... python scripts/seed_demo.py
"""
import asyncio
import asyncpg
import os

DEMO_USER = {
    "firebase_uid": "demo-user-001",
    "email": "demo@example.com",
    "display_name": "Demo User",
}

DEMO_FOLDERS = [
    {"name": "Technical Docs", "color": "#3B82F6", "icon": "📘"},
    {"name": "Research Papers", "color": "#8B5CF6", "icon": "📄"},
    {"name": "Contracts", "color": "#F59E0B", "icon": "📋"},
]


async def seed():
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        user_id = await conn.fetchval(
            """INSERT INTO users (firebase_uid, email, display_name)
               VALUES ($1, $2, $3)
               ON CONFLICT (firebase_uid) DO UPDATE SET email = EXCLUDED.email
               RETURNING id""",
            DEMO_USER["firebase_uid"], DEMO_USER["email"], DEMO_USER["display_name"],
        )
        print(f"Demo user: {user_id}")

        for folder in DEMO_FOLDERS:
            fid = await conn.fetchval(
                """INSERT INTO folders (user_id, name, color, icon)
                   VALUES ($1, $2, $3, $4)
                   ON CONFLICT (user_id, name) DO NOTHING
                   RETURNING id""",
                user_id, folder["name"], folder["color"], folder["icon"],
            )
            print(f"  Folder '{folder['name']}': {fid}")

        print("Seed complete.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(seed())
