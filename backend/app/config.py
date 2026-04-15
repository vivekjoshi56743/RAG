from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://user:password@localhost/ragdb"

    # GCS
    gcs_bucket: str = "rag-documents"

    # Firebase
    firebase_project_id: str = ""
    vertex_project_id: str = ""
    vertex_location: str = "us-central1"

    # Local development auth shortcut (skips Firebase verification)
    dev_auth_enabled: bool = False
    dev_auth_token: str = "local-dev-token"
    dev_auth_uid: str = "local-dev-user"
    dev_auth_email: str = "local@example.com"

    # API keys
    voyage_api_key: str = ""
    anthropic_api_key: str = ""

    # LLM provider control
    llm_primary_provider: str = "anthropic"   # anthropic | vertex
    llm_fallback_provider: str = "vertex"     # anthropic | vertex

    # Anthropic models
    anthropic_chat_model: str = "claude-sonnet-4-20250514"
    anthropic_summary_model: str = "claude-sonnet-4-20250514"
    anthropic_rewrite_model: str = "claude-sonnet-4-20250514"
    anthropic_enrich_model: str = "claude-sonnet-4-20250514"
    anthropic_rerank_model: str = "claude-sonnet-4-20250514"

    # Vertex models
    vertex_chat_model: str = "gemini-2.5-pro"
    vertex_summary_model: str = "gemini-2.5-pro"
    vertex_rewrite_model: str = "gemini-2.5-pro"
    vertex_enrich_model: str = "gemini-2.5-pro"
    vertex_rerank_model: str = "gemini-2.5-pro"
    vertex_embedding_model: str = "gemini-embedding-001"

    # Vertex Ranking API (Discovery Engine ranking config path)
    # Example:
    # projects/<project>/locations/global/rankingConfigs/default_ranking_config
    vertex_ranking_config: str = ""
    vertex_ranking_model: str = "semantic-ranker-512@latest"

    # Embedding output dimensions
    embedding_dimensions: int = 768

    # Embedding/chunking profile (quality | balanced | fast)
    embedding_model_profile: str = "quality"

    # Embedding request controls (set to override profile defaults)
    embedding_chars_per_token: int | None = None
    embedding_max_tokens_per_input: int | None = None
    embedding_max_tokens_per_request: int | None = None
    embedding_max_items_per_request: int | None = None

    # Chunking controls (set to override profile defaults)
    chunk_target_tokens: int | None = None
    chunk_overlap_tokens: int | None = None
    chunk_chars_per_token: int | None = None
    chunk_semantic_min_sentences: int | None = None
    chunk_semantic_boundary_threshold: float | None = None
    chunk_semantic_embedding_batch_size: int | None = None
    chunk_structure_sample_chars: int | None = None
    chunk_structured_heading_density_threshold: float | None = None
    chunk_mixed_heading_density_threshold: float | None = None

    # Parser extraction controls
    # `extract_pdf_text_density_threshold` is the minimum native character count
    # on a PDF page before we fall back to Cloud Vision OCR. Low values (like
    # the old 50) over-trigger OCR on pages that legitimately have only a title
    # plus one line; 120 avoids most false positives while still catching true
    # scans.
    extract_pdf_text_density_threshold: int = 120
    extract_virtual_page_char_limit: int = 3000

    # Cloud Vision OCR language hints (ISO 639-1 codes). Example: ["en", "de"].
    ocr_language_hints: list[str] = ["en"]

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    # App
    environment: str = "development"
    debug: bool = False

    class Config:
        env_file = ".env"


settings = Settings()
