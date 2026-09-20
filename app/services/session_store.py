from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID, uuid4

from app.core.config import Settings
from app.core.exceptions import SessionNotFoundError


def get_session_root(settings: Settings) -> Path:
    root = settings.upload.data_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def create_session(settings: Settings) -> tuple[str, Path]:
    session_id = str(uuid4())
    directory = get_session_root(settings) / session_id
    directory.mkdir(parents=True)
    return session_id, directory


def get_session_directory(settings: Settings, session_id: str) -> Path:
    try:
        canonical_id = str(UUID(session_id))
    except ValueError as exc:
        raise SessionNotFoundError("Session not found") from exc
    directory = get_session_root(settings) / canonical_id
    if not directory.is_dir():
        raise SessionNotFoundError("Session not found")
    return directory


def get_database_path(settings: Settings, session_id: str) -> Path:
    return get_session_directory(settings, session_id) / "data.duckdb"


def save_metadata(settings: Settings, session_id: str, metadata: dict) -> None:
    path = get_session_directory(settings, session_id) / "metadata.json"
    path.write_text(json.dumps(metadata, indent=2, default=str), encoding="utf-8")


def load_metadata(settings: Settings, session_id: str) -> dict:
    path = get_session_directory(settings, session_id) / "metadata.json"
    if not path.exists():
        raise SessionNotFoundError("Session metadata not found")
    return json.loads(path.read_text(encoding="utf-8"))

