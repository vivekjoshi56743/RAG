"""
Scheduled Cloud Run Job: refresh materialized views used for user preference scoring.

Runs every 15 minutes via Cloud Scheduler.
Refreshes:
  - user_chunk_preferences
  - user_document_preferences
"""
import asyncio
import asyncpg
from app.config import settings


async def refresh_materialized_views() -> None:
    conn = await asyncpg.connect(settings.database_url.replace("+asyncpg", ""))
    try:
        await conn.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY user_chunk_preferences")
        await conn.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY user_document_preferences")
        print("Materialized views refreshed successfully.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(refresh_materialized_views())
