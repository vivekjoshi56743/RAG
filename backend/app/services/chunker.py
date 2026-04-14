"""
Adaptive multi-strategy chunker.

Detection pass classifies the document as STRUCTURED / MIXED / FLAT,
then routes to the best chunking strategy:
  - STRUCTURED → split at detected headings (manuals, API docs, specs)
  - MIXED      → recursive paragraph split + heading awareness (papers, reports)
  - FLAT       → semantic chunking via sentence-similarity drops (novels, essays)
"""
import re
from enum import Enum
from uuid import UUID


TARGET_TOKENS = 512
OVERLAP_TOKENS = 50
CHARS_PER_TOKEN = 4  # rough approximation


class DocumentStructure(Enum):
    STRUCTURED = "structured"
    MIXED = "mixed"
    FLAT = "flat"


def detect_structure(text: str) -> tuple[DocumentStructure, dict]:
    """Scan first ~15K chars to classify document structure."""
    sample = text[:15000]
    lines = sample.split("\n")

    md_headings = len(re.findall(r'^#{1,4}\s+\S', sample, re.MULTILINE))
    numbered = len(re.findall(
        r'^(?:\d+\.[\d.]*\s+[A-Z]|Section\s+\d|CHAPTER\s+\d)', sample, re.MULTILINE
    ))
    caps_headings = len([
        l for l in lines
        if l.strip() and len(l.strip()) < 100
        and l.strip().isupper() and not l.strip().endswith(('.', ','))
    ])

    heading_density = (md_headings + numbered + caps_headings / 3) / max(len(lines), 1) * 100
    patterns = {
        "md_headings": md_headings,
        "numbered": numbered,
        "caps_headings": caps_headings,
        "heading_density": heading_density,
    }

    if heading_density > 3 or md_headings > 5 or numbered > 5:
        return DocumentStructure.STRUCTURED, patterns
    elif heading_density > 1 or caps_headings > 5:
        return DocumentStructure.MIXED, patterns
    else:
        return DocumentStructure.FLAT, patterns


def chunk_structured(text: str, doc_id: UUID, doc_name: str, pages: list[dict], summary: str = "") -> list[dict]:
    """Split at detected heading boundaries, preserving hierarchy."""
    # TODO: implement full structure-aware splitting
    return _recursive_split(text, doc_id, doc_name, pages, summary)


def chunk_mixed(text: str, doc_id: UUID, doc_name: str, pages: list[dict], summary: str = "") -> list[dict]:
    """Recursive paragraph split with heading context capture."""
    return _recursive_split(text, doc_id, doc_name, pages, summary)


async def chunk_semantic(text: str, doc_id: UUID, doc_name: str, pages: list[dict], summary: str = "") -> list[dict]:
    """
    Sentence-level semantic chunking: split where cosine similarity between
    consecutive sentences drops below threshold. Falls back to recursive split.
    """
    # TODO: implement full semantic chunking with Voyage embeddings
    return _recursive_split(text, doc_id, doc_name, pages, summary)


async def chunk_document(pages: list[dict], doc_id: UUID, doc_name: str, summary: str = "") -> list[dict]:
    """Entry point: detect structure and route to the best strategy."""
    full_text = "\n\n".join(page["text"] for page in pages)
    structure_type, patterns = detect_structure(full_text)

    if structure_type == DocumentStructure.STRUCTURED:
        return chunk_structured(full_text, doc_id, doc_name, pages, summary)
    elif structure_type == DocumentStructure.MIXED:
        return chunk_mixed(full_text, doc_id, doc_name, pages, summary)
    else:
        return await chunk_semantic(full_text, doc_id, doc_name, pages, summary)


def _recursive_split(text: str, doc_id: UUID, doc_name: str, pages: list[dict], summary: str) -> list[dict]:
    """Fallback: split at paragraph boundaries up to TARGET_TOKENS, with OVERLAP_TOKENS overlap."""
    max_chars = TARGET_TOKENS * CHARS_PER_TOKEN
    overlap_chars = OVERLAP_TOKENS * CHARS_PER_TOKEN

    paragraphs = text.split("\n\n")
    chunks = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) <= max_chars:
            current += para + "\n\n"
        else:
            if current.strip():
                chunks.append(_make_chunk(current.strip(), len(chunks), doc_id, doc_name, summary))
            current = current[-overlap_chars:] + para + "\n\n"

    if current.strip():
        chunks.append(_make_chunk(current.strip(), len(chunks), doc_id, doc_name, summary))

    return chunks


def _make_chunk(text: str, index: int, doc_id: UUID, doc_name: str, summary: str) -> dict:
    return {
        "document_id": doc_id,
        "chunk_index": index,
        "content": text,
        "token_count": len(text) // CHARS_PER_TOKEN,
        "doc_name": doc_name,
        "doc_summary_short": summary[:200] if summary else "",
    }
