"""Runtime settings for the converters backend.

All values can be overridden with environment variables prefixed CONVERTER_ or .env file.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CONVERTER_", env_file=".env", extra="ignore")

    work_dir: Path = Path(tempfile.gettempdir()) / "cdif-converters"
    default_max_rows: int = 5
    upload_ttl_seconds: int = 6 * 3600
    api_key: str | None = None
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000", "*"]


settings = Settings()
