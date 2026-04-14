"""
Auto-generate a structured summary for each uploaded document.
Runs once per document after text extraction, before embedding.
"""
import json
import anthropic
from app.config import settings


async def generate_summary(text: str, doc_name: str) -> dict:
    """
    Returns:
        summary:       2–3 sentence overview
        key_topics:    3–5 main topics (short phrases)
        document_type: legal | technical | academic | business | general
    """
    excerpt = text[:16000]  # ~4K tokens
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": (
                f'Analyze this document and return a JSON object with:\n'
                f'- "summary": 2-3 sentence overview\n'
                f'- "key_topics": array of 3-5 main topics (short phrases)\n'
                f'- "document_type": one of ["legal","technical","academic","business","general"]\n\n'
                f'Document: "{doc_name}"\n\n{excerpt}\n\n'
                f'Respond ONLY with valid JSON, no markdown fences.'
            ),
        }],
    )

    try:
        return json.loads(response.content[0].text)
    except json.JSONDecodeError:
        return {
            "summary": response.content[0].text[:300],
            "key_topics": [],
            "document_type": "general",
        }
