from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "SignalFeed"
    API_V1_STR: str = "/api"

    # Database
    DATABASE_URL: str = "postgresql://feed_user:feed_password@db:5432/feed_db"

    # ML & Vector Settings (Nemotron Default API-Driven)
    EMBEDDING_PROVIDER: str = "nvidia"
    EMBEDDING_MODEL: str = "nvidia/llama-nemotron-embed-vl-1b-v2"
    EMBEDDING_DIM: int = 2048
    EMBEDDING_VERSION: str = "v2"
    EMBEDDING_BATCH_SIZE: int = 16
    EMBEDDING_CACHE_ENABLED: bool = True

    # Custom API Credentials
    NVIDIA_API_EMBEDDING: Optional[str] = None  # Key for embedding API
    NVIDIA_API_KEY1: Optional[str] = None       # Key for other NVIDIA models
    NVIDIA_API_KEY: Optional[str] = None        # General fallback key
    OPENAI_API_KEY: Optional[str] = None

    # Ingestion rate controls
    DEFAULT_POLLING_INTERVAL_MINS: int = 360
    MAX_PROCESSING_RETRIES: int = 3

    # Discovery Target Engine
    DISCOVERY_RATIO_TARGET: float = 0.20
    DISCOVERY_ROLLING_WINDOW_SIZE: int = 50

    # Ollama integration
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_SUMMARY_MODEL: str = "llama3"

    # CORS origins
    BACKEND_CORS_ORIGINS: list[str] = ["*"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
