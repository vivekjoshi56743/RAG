from __future__ import annotations

from typing import TypedDict


class ModelProfile(TypedDict):
    embedding_chars_per_token: int
    embedding_max_tokens_per_input: int
    embedding_max_tokens_per_request: int
    embedding_max_items_per_request: int
    chunk_target_tokens: int
    chunk_overlap_tokens: int
    chunk_chars_per_token: int
    chunk_semantic_min_sentences: int
    chunk_semantic_boundary_threshold: float
    chunk_semantic_embedding_batch_size: int
    chunk_structure_sample_chars: int
    chunk_structured_heading_density_threshold: float
    chunk_mixed_heading_density_threshold: float


_PROFILES: dict[str, ModelProfile] = {
    "quality": {
        "embedding_chars_per_token": 4,
        "embedding_max_tokens_per_input": 1800,
        "embedding_max_tokens_per_request": 14000,
        "embedding_max_items_per_request": 80,
        "chunk_target_tokens": 420,
        "chunk_overlap_tokens": 60,
        "chunk_chars_per_token": 4,
        "chunk_semantic_min_sentences": 6,
        "chunk_semantic_boundary_threshold": 0.30,
        "chunk_semantic_embedding_batch_size": 64,
        "chunk_structure_sample_chars": 15000,
        "chunk_structured_heading_density_threshold": 3.0,
        "chunk_mixed_heading_density_threshold": 1.0,
    },
    "balanced": {
        "embedding_chars_per_token": 4,
        "embedding_max_tokens_per_input": 1850,
        "embedding_max_tokens_per_request": 16000,
        "embedding_max_items_per_request": 120,
        "chunk_target_tokens": 512,
        "chunk_overlap_tokens": 50,
        "chunk_chars_per_token": 4,
        "chunk_semantic_min_sentences": 6,
        "chunk_semantic_boundary_threshold": 0.30,
        "chunk_semantic_embedding_batch_size": 96,
        "chunk_structure_sample_chars": 15000,
        "chunk_structured_heading_density_threshold": 3.0,
        "chunk_mixed_heading_density_threshold": 1.0,
    },
    "fast": {
        "embedding_chars_per_token": 4,
        "embedding_max_tokens_per_input": 1900,
        "embedding_max_tokens_per_request": 18000,
        "embedding_max_items_per_request": 160,
        "chunk_target_tokens": 640,
        "chunk_overlap_tokens": 40,
        "chunk_chars_per_token": 4,
        "chunk_semantic_min_sentences": 5,
        "chunk_semantic_boundary_threshold": 0.25,
        "chunk_semantic_embedding_batch_size": 128,
        "chunk_structure_sample_chars": 15000,
        "chunk_structured_heading_density_threshold": 3.0,
        "chunk_mixed_heading_density_threshold": 1.0,
    },
}


def get_model_profile(name: str) -> ModelProfile:
    return _PROFILES.get((name or "").strip().lower(), _PROFILES["quality"])
