"""
Auto-generate a short, descriptive title for a new conversation after its
first user/assistant exchange.

Runs as a best-effort background task; failures are swallowed and the
conversation keeps its default 'New Chat' title.
"""
import logging
from uuid import UUID

from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.services.llm_provider import complete_text

logger = logging.getLogger(__name__)

MAX_TITLE_LEN = 120


def _sanitize_title(raw: str) -> str:
    """Strip quotes, trailing punctuation, clamp length."""
    title = raw.strip()
    # Models sometimes wrap output in quotes or prefix "Title:"
    if title.lower().startswith("title:"):
        title = title[6:].strip()
    title = title.strip('"').strip("'").strip("`").strip()
    # Strip a single trailing period (keep ! and ?)
    if title.endswith("."):
        title = title[:-1].rstrip()
    # Collapse internal newlines into a single space
    title = " ".join(title.split())
    return title[:MAX_TITLE_LEN]


async def _generate_title(first_user_msg: str, first_assistant_msg: str) -> str:
    prompt = (
        "You are naming a chat thread. Summarize the exchange below as a short "
        "title of 3 to 6 words. Use title case. No quotes. No trailing period. "
        "Do not start with 'Chat about' or 'Discussion of'. Return ONLY the title.\n\n"
        f"User: {first_user_msg[:600]}\n\n"
        f"Assistant: {first_assistant_msg[:400]}"
    )
    text_out, _provider = await complete_text(
        "rewrite",
        prompt,
        max_tokens=30,
        temperature=0.2,
    )
    return _sanitize_title(text_out)


async def maybe_autotitle_conversation(
    conv_id: UUID,
    first_user_msg: str,
    first_assistant_msg: str,
) -> str | None:
    """
    Best-effort: generate and persist a title for conversation `conv_id` only
    if it is still called 'New Chat'. Returns the new title on success, else None.
    Never raises.
    """
    try:
        async with AsyncSessionLocal() as db:
            row = (
                await db.execute(
                    text("SELECT title FROM conversations WHERE id = :id"),
                    {"id": str(conv_id)},
                )
            ).mappings().first()
            if not row or (row["title"] or "").strip() != "New Chat":
                return None

            title = await _generate_title(first_user_msg, first_assistant_msg)
            if not title:
                return None

            await db.execute(
                text("UPDATE conversations SET title = :title, updated_at = now() WHERE id = :id"),
                {"id": str(conv_id), "title": title},
            )
            await db.commit()
            return title
    except Exception:
        logger.exception("Auto-title failed for conversation %s", conv_id)
        return None
