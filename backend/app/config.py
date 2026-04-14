from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://user:password@localhost/ragdb"

    # GCS
    gcs_bucket: str = "rag-documents"

    # Firebase
    firebase_project_id: str = ""

    # Local development auth shortcut (skips Firebase verification)
    dev_auth_enabled: bool = False
    dev_auth_token: str = "local-dev-token"
    dev_auth_uid: str = "local-dev-user"
    dev_auth_email: str = "local@example.com"

    # API keys
    voyage_api_key: str = ""
    cohere_api_key: str = ""
    anthropic_api_key: str = ""

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    # App
    environment: str = "development"
    debug: bool = False

    class Config:
        env_file = ".env"


settings = Settings()
