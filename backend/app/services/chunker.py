"""
Adaptive multi-strategy chunker.

Detection pass classifies the document as STRUCTURED / MIXED / FLAT,
then routes to the best chunking strategy:
  - STRUCTURED → split at detected headings (manuals, API docs, specs)
  - MIXED      → recursive paragraph split + heading awareness (papers, reports)
  - FLAT       → semantic chunking via sentence-similarity drops (novels, essays)
"""
import re
import math
from enum import Enum
from uuid import UUID

from app.config import settings
from app.services.model_profiles import get_model_profile


def _profile() -> dict:
    return get_model_profile(settings.embedding_model_profile)


def _chunk_target_tokens() -> int:
    profile = _profile()
    return max(1, settings.chunk_target_tokens or profile["chunk_target_tokens"])


def _chunk_overlap_tokens() -> int:
    profile = _profile()
    return max(0, settings.chunk_overlap_tokens or profile["chunk_overlap_tokens"])


def _chunk_chars_per_token() -> int:
    profile = _profile()
    return max(1, settings.chunk_chars_per_token or profile["chunk_chars_per_token"])


def _chunk_semantic_min_sentences() -> int:
    profile = _profile()
    return max(2, settings.chunk_semantic_min_sentences or profile["chunk_semantic_min_sentences"])


def _chunk_semantic_boundary_threshold() -> float:
    profile = _profile()
    return settings.chunk_semantic_boundary_threshold or profile["chunk_semantic_boundary_threshold"]


def _chunk_semantic_embedding_batch_size() -> int:
    profile = _profile()
    return max(1, settings.chunk_semantic_embedding_batch_size or profile["chunk_semantic_embedding_batch_size"])


def _chunk_structure_sample_chars() -> int:
    profile = _profile()
    return max(1000, settings.chunk_structure_sample_chars or profile["chunk_structure_sample_chars"])


def _chunk_structured_heading_density_threshold() -> float:
    profile = _profile()
    return settings.chunk_structured_heading_density_threshold or profile["chunk_structured_heading_density_threshold"]


def _chunk_mixed_heading_density_threshold() -> float:
    profile = _profile()
    return settings.chunk_mixed_heading_density_threshold or profile["chunk_mixed_heading_density_threshold"]


class DocumentStructure(Enum):
    STRUCTURED = "structured"
    MIXED = "mixed"
    FLAT = "flat"


def detect_structure(text: str) -> tuple[DocumentStructure, dict]:
    """Scan first ~15K chars to classify document structure."""
    sample = text[:_chunk_structure_sample_chars()]
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

    if heading_density > _chunk_structured_heading_density_threshold() or md_headings > 5 or numbered > 5:
        return DocumentStructure.STRUCTURED, patterns
    elif heading_density > _chunk_mixed_heading_density_threshold() or caps_headings > 5:
        return DocumentStructure.MIXED, patterns
    else:
        return DocumentStructure.FLAT, patterns


def chunk_structured(text: str, doc_id: UUID, doc_name: str, pages: list[dict], summary: str = "") -> list[dict]:
    """Split at detected heading boundaries, preserving hierarchy."""
    heading_pattern = re.compile(
        r"(?m)^(?:#{1,4}\s+.+|(?:\d+\.[\d.]*\s+.+)|(?:Section\s+\d+.*)|(?:CHAPTER\s+\d+.*)|(?:[A-Z][A-Z0-9\s\-]{3,}))$"
    )
    matches = list(heading_pattern.finditer(text))
    if len(matches) < 2:
        return _recursive_split(text, doc_id, doc_name, pages, summary)

    chunks: list[dict] = []
    for idx, match in enumerate(matches):
        section_start = match.start()
        section_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        section_heading = match.group(0).strip().lstrip("#").strip()
        section_body = text[section_start:section_end].strip()
        if not section_body:
            continue

        # Keep section-level context and recursively split if too large.
        section_chunks = _recursive_split(section_body, doc_id, doc_name, pages, summary)
        for section_chunk in section_chunks:
            section_chunk["section_heading"] = section_heading
            chunks.append(section_chunk)
    return chunks or _recursive_split(text, doc_id, doc_name, pages, summary)


def chunk_mixed(text: str, doc_id: UUID, doc_name: str, pages: list[dict], summary: str = "") -> list[dict]:
    """Recursive paragraph split with heading context capture."""
    return _recursive_split(text, doc_id, doc_name, pages, summary)


async def chunk_semantic(text: str, doc_id: UUID, doc_name: str, pages: list[dict], summary: str = "") -> list[dict]:
    """
    Sentence-level semantic chunking: split where cosine similarity between
    consecutive sentences drops below threshold. Falls back to recursive split.
    """
    from app.services.embedder import embed_documents

    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
    if len(sentences) < _chunk_semantic_min_sentences():
        return _recursive_split(text, doc_id, doc_name, pages, summary)

    try:
        sentence_embeddings = await embed_documents(sentences, batch_size=_chunk_semantic_embedding_batch_size())
    except Exception:
        return _recursive_split(text, doc_id, doc_name, pages, summary)

    max_chars = _chunk_target_tokens() * _chunk_chars_per_token()
    chunks: list[str] = []
    current = [sentences[0]]
    current_len = len(sentences[0])

    for idx in range(1, len(sentences)):
        sim = _cosine_similarity(sentence_embeddings[idx - 1], sentence_embeddings[idx])
        sentence = sentences[idx]
        boundary = sim < _chunk_semantic_boundary_threshold()

        if boundary or (current_len + len(sentence) > max_chars):
            chunks.append(" ".join(current).strip())
            overlap_chars = _chunk_overlap_tokens() * _chunk_chars_per_token()
            overlap_tail = " ".join(current)[-overlap_chars:] if overlap_chars > 0 else ""
            current = [overlap_tail, sentence] if overlap_tail else [sentence]
            current_len = sum(len(x) for x in current)
        else:
            current.append(sentence)
            current_len += len(sentence)

    if current:
        chunks.append(" ".join(current).strip())

    return [_make_chunk(c, i, doc_id, doc_name, summary) for i, c in enumerate(chunks) if c]


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
    max_chars = _chunk_target_tokens() * _chunk_chars_per_token()
    overlap_chars = _chunk_overlap_tokens() * _chunk_chars_per_token()

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
        "token_count": len(text) // _chunk_chars_per_token(),
        "doc_name": doc_name,
        # Richer contextual prefix embedded into each chunk's embedding text.
        # Caller is expected to pass a combined "summary + key topics" string;
        # 400 chars is enough for ~5 sentences + a topics line without bloating
        # embedding cost.
        "doc_summary_short": summary[:400] if summary else "",
    }


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    a_mag = math.sqrt(sum(x * x for x in a))
    b_mag = math.sqrt(sum(y * y for y in b))
    if a_mag == 0.0 or b_mag == 0.0:
        return 0.0
    return dot / (a_mag * b_mag)
