"""
Auto-generate a structured summary for each uploaded document.
Runs once per document after text extraction, before embedding.

Strategy:
  - Short docs (≤ SINGLE_PASS_CHAR_LIMIT): single LLM call.
  - Long docs: map-reduce — summarize overlapping windows in parallel, then
    synthesize the window summaries into the final output. This stops very
    long documents from being summarized from just their first ~4K tokens.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re

from app.services.llm_provider import complete_text

logger = logging.getLogger(__name__)

SINGLE_PASS_CHAR_LIMIT = 16000       # ~4K tokens — fits in one shot comfortably
WINDOW_SIZE = 12000                  # map-phase window size
WINDOW_OVERLAP = 500                 # small overlap so cross-window facts survive
MAX_WINDOWS = 12                     # cap map-phase fan-out to control cost
REDUCE_BUDGET_CHARS = 16000          # max chars fed into the reduce prompt


def _final_prompt(excerpt: str, doc_name: str) -> str:
    return (
        "Analyze this document and return a single JSON object with these fields:\n"
        '- "summary": 5 to 8 sentences capturing what the document is about, its main arguments or findings, and its scope. Prefer concrete details over generic phrases.\n'
        '- "key_topics": array of 5 to 10 specific topic phrases (not single generic words).\n'
        '- "entities": array of up to 15 important named entities — people, organizations, places, products, laws, systems. Omit if none.\n'
        '- "document_type": one of ["legal","technical","academic","business","general"].\n'
        '- "subtype": a short free-text label more specific than document_type (e.g. "API reference", "quarterly earnings call transcript", "novel — satirical fiction"). Omit if unsure.\n\n'
        f'Document: "{doc_name}"\n\n'
        f"{excerpt}\n\n"
        "Respond ONLY with valid JSON, no markdown fences, no commentary."
    )


def _map_prompt(window: str, doc_name: str, window_idx: int, total: int) -> str:
    return (
        f'Document: "{doc_name}" — section {window_idx + 1} of {total}.\n\n'
        "Write a dense 4 to 6 sentence summary of this section. Capture the specific "
        "facts, names, numbers, and arguments present here. Do not speculate about other "
        "sections. No preamble, no bullet list — just the summary prose.\n\n"
        f"{window}"
    )


def _default_fallback(text: str) -> dict:
    return {
        "summary": (text or "")[:400],
        "key_topics": [],
        "entities": [],
        "document_type": "general",
        "subtype": None,
    }


def _strip_json_fences(raw: str) -> str:
    """Remove ```json ... ``` fences the model sometimes adds anyway."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].rstrip()
    return cleaned


def _parse_summary_json(raw: str) -> dict:
    try:
        data = json.loads(_strip_json_fences(raw))
    except json.JSONDecodeError:
        logger.warning("Summarizer JSON parse failed; using fallback")
        return _default_fallback(raw)
    if not isinstance(data, dict):
        return _default_fallback(raw)
    # Normalize — tolerate missing keys.
    return {
        "summary": str(data.get("summary") or "")[:4000],
        "key_topics": [str(x) for x in (data.get("key_topics") or []) if x][:10],
        "entities": [str(x) for x in (data.get("entities") or []) if x][:15],
        "document_type": str(data.get("document_type") or "general"),
        "subtype": (str(data.get("subtype")) if data.get("subtype") else None),
    }


def _split_windows(text: str) -> list[str]:
    """Split text into overlapping windows, capped at MAX_WINDOWS."""
    if len(text) <= SINGLE_PASS_CHAR_LIMIT:
        return [text]
    step = max(1, WINDOW_SIZE - WINDOW_OVERLAP)
    raw = [text[i:i + WINDOW_SIZE] for i in range(0, len(text), step) if text[i:i + WINDOW_SIZE]]
    if len(raw) <= MAX_WINDOWS:
        return raw
    # Evenly subsample to stay under MAX_WINDOWS while preserving head/tail.
    indices = [round(i * (len(raw) - 1) / (MAX_WINDOWS - 1)) for i in range(MAX_WINDOWS)]
    seen: set[int] = set()
    sampled: list[str] = []
    for idx in indices:
        if idx not in seen:
            seen.add(idx)
            sampled.append(raw[idx])
    return sampled


async def _summarize_window(window: str, doc_name: str, idx: int, total: int) -> str:
    prompt = _map_prompt(window, doc_name, idx, total)
    try:
        text_out, _ = await complete_text(
            "summary",
            prompt,
            max_tokens=400,
            temperature=0.0,
        )
        return text_out.strip()
    except Exception:
        logger.exception("Map-phase window summary failed (idx=%d)", idx)
        return ""


async def generate_summary(text: str, doc_name: str) -> dict:
    """
    Returns:
        summary:       5–8 sentence overview
        key_topics:    5–10 specific topic phrases
        entities:      up to 15 named entities (people/orgs/places/…)
        document_type: legal | technical | academic | business | general
        subtype:       free-text refinement (e.g. "API reference"), may be None
    """
    if not (text or "").strip():
        return _default_fallback("")

    if len(text) <= SINGLE_PASS_CHAR_LIMIT:
        prompt = _final_prompt(text, doc_name)
        try:
            raw, _ = await complete_text(
                "summary",
                prompt,
                max_tokens=1200,
                temperature=0.0,
            )
            return _parse_summary_json(raw)
        except Exception:
            logger.exception("Single-pass summarizer failed")
            return _default_fallback(text[:400])

    # Map phase: summarize each window concurrently.
    windows = _split_windows(text)
    map_results = await asyncio.gather(
        *[_summarize_window(w, doc_name, i, len(windows)) for i, w in enumerate(windows)],
        return_exceptions=False,
    )
    partials = [m for m in map_results if m]

    if not partials:
        # All map calls failed — fall back to head-only single-pass.
        logger.warning("All map-phase summaries empty; falling back to head-only")
        return await generate_summary(text[:SINGLE_PASS_CHAR_LIMIT], doc_name)

    # Reduce phase: feed the partials into the final JSON prompt.
    joined = "\n\n".join(
        f"[Section {i + 1}]\n{p}" for i, p in enumerate(partials)
    )
    if len(joined) > REDUCE_BUDGET_CHARS:
        joined = joined[:REDUCE_BUDGET_CHARS]

    reduce_prompt = _final_prompt(joined, doc_name) + (
        "\n\nNote: The text above is a set of per-section summaries of the real document. "
        "Synthesize across all sections — do not treat any one section as the whole document."
    )
    try:
        raw, _ = await complete_text(
            "summary",
            reduce_prompt,
            max_tokens=1200,
            temperature=0.0,
        )
        return _parse_summary_json(raw)
    except Exception:
        logger.exception("Reduce-phase summary failed; returning joined partials as fallback")
        return {
            "summary": partials[0][:1000],
            "key_topics": [],
            "entities": [],
            "document_type": "general",
            "subtype": None,
        }
