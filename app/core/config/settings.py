from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseModel):
    name: str
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False


class ModelConfig(BaseModel):
    name: str
    temperature: float = 0.0
    max_retries: int = 2


class UploadConfig(BaseModel):
    data_dir: Path = Path("data/sessions")
    allowed_extensions: list[str] = Field(default_factory=lambda: [".csv", ".xlsx"])
    max_file_size_mb: int = 25
    max_files: int = 10
    header_scan_rows: int = 12
    min_table_rows: int = 2
    detection_confidence_threshold: float = 0.65


class QueryConfig(BaseModel):
    row_limit: int = 200
    preview_rows: int = 3
    max_agent_attempts: int = 3
    max_agent_steps: int = 6
    join_hint_threshold: float = 0.55
    max_prompt_chars: int = 24_000


class Settings(BaseSettings):
    """Environment secrets plus non-secret settings loaded from config.json."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    groq_api_key: str = ""
    config_path: Path = Path("config.json")
    app: AppConfig
    model: ModelConfig
    upload: UploadConfig
    query: QueryConfig


def load_settings() -> Settings:
    config_path = Path(os.getenv("CONFIG_PATH", "config.json"))
    if not config_path.is_absolute():
        config_path = Path.cwd() / config_path
    if not config_path.exists():
        raise RuntimeError(f"Configuration file not found: {config_path}")
    with config_path.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    return Settings(config_path=config_path, **raw)


@lru_cache
def get_settings() -> Settings:
    return load_settings()
