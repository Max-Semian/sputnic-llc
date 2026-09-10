"""Application configuration (core layer).

Single source of truth for runtime settings: env vars via pydantic-settings,
full-URL override for tests. No engines/IO are created here.
"""

from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    # --- Database -------------------------------------------------------
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_db: str = "test"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # Full URL override (highest priority). Used by tests (SQLite) and
    # deployments that prefer a single DSN instead of the components above.
    database_url: str | None = None

    # --- Task queue -----------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"

    # --- Storage --------------------------------------------------------
    storage_dir: Path = Path(__file__).resolve().parents[2] / "storage" / "files"
    max_upload_size: int = 512 * 1024 * 1024  # 512 MB
    chunk_size: int = 1024 * 1024  # 1 MB stream chunks

    # --- HTTP -----------------------------------------------------------
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    @property
    def async_database_url(self) -> str:
        """URL used by the async engine (asyncpg / aiosqlite in tests)."""
        if self.database_url:
            return self.database_url
        creds = f"{self.postgres_user}:{quote_plus(self.postgres_password)}"
        return (
            f"postgresql+asyncpg://{creds}@{self.postgres_host}:"
            f"{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
