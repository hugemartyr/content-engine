import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Project Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent

    # Local Model Configuration
    USE_LOCAL_LLM: bool = False
    LOCAL_LLM_URL: str = "http://localhost:11434/v1"
    LOCAL_LLM_MODEL: str = "qwen2.5vl:7b"

    # API Keys
    GEMINI_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None

    # External APIs
    GITHUB_TOKEN: Optional[str] = None
    PEXELS_API_KEY: Optional[str] = None
    PIXABAY_API_KEY: Optional[str] = None

    # Database
    DB_PROVIDER: str = "sqlite"  # 'postgres' or 'sqlite'
    SQLITE_PATH: str = "./data/engine.db"
    DATABASE_URL: str = "postgresql+asyncpg://content_user:content_password@localhost:5435/content_intelligence"

    # Vector Search
    VECTOR_PROVIDER: str = "memory"  # 'qdrant' or 'memory'
    QDRANT_URL: str = "http://localhost:6334"

    # Queue/Cache
    QUEUE_PROVIDER: str = "memory"  # 'redis' or 'memory'
    REDIS_URL: str = "redis://localhost:6380/0"

    # Logging & Environment
    LOG_LEVEL: str = "INFO"
    ENV: str = "development"

    # LangSmith Observability
    LANGCHAIN_TRACING_V2: bool = False
    LANGCHAIN_API_KEY: Optional[str] = None
    LANGCHAIN_PROJECT: str = "content-intelligence-engine"

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def get_db_url(self) -> str:
        if self.DB_PROVIDER == "sqlite":
            # Ensure SQLite dir exists
            path = Path(self.SQLITE_PATH)
            if not path.is_absolute():
                path = self.BASE_DIR / path
            path.parent.mkdir(parents=True, exist_ok=True)
            return f"sqlite+aiosqlite:///{path}"
        return self.DATABASE_URL

settings = Settings()
