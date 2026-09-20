from __future__ import annotations

import io
import re
from collections.abc import Iterable
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
from fastapi import UploadFile

from app.core.config import Settings
from app.core.exceptions import UploadValidationError
from app.schemas.api import JoinHint, TableSummary, UploadResponse
from app.services.session_store import create_session, save_metadata


def safe_identifier(value: str, fallback: str = "table") -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    if not cleaned:
        cleaned = fallback
    if cleaned[0].isdigit():
        cleaned = f"t_{cleaned}"
    return cleaned[:63]


def _unique_name(base: str, used: set[str]) -> str:
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}_{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _normalise_dataframe(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    used: set[str] = set()
    frame.columns = [
        _unique_name(safe_identifier(str(column), f"column_{index + 1}"), used)
        for index, column in enumerate(frame.columns)
    ]
    for column in frame.select_dtypes(include=["object"]).columns:
        values = frame[column].dropna().astype(str)
        if values.empty:
            continue
        parsed = pd.to_datetime(values, errors="coerce", format="mixed")
        if parsed.notna().mean() >= 0.9:
            frame[column] = pd.to_datetime(frame[column], errors="coerce", format="mixed")
    return frame


def _profile(frame: pd.DataFrame, preview_rows: int) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    for column in frame.columns:
        series = frame[column]
        samples = series.dropna().astype(str).drop_duplicates().head(preview_rows).tolist()
        profiles.append(
            {
                "name": str(column),
                "dtype": str(series.dtype),
                "null_pct": round(float(series.isna().mean()), 4),
                "distinct": int(series.nunique(dropna=True)),
                "samples": samples,
            }
        )
    return profiles


def _overlap(left: pd.Series, right: pd.Series) -> float:
    left_values = set(left.dropna().astype(str).str.lower().head(200))
    right_values = set(right.dropna().astype(str).str.lower().head(200))
    smaller = min(len(left_values), len(right_values))
    return len(left_values & right_values) / smaller if smaller else 0.0


def infer_join_hints(
    frames: dict[str, pd.DataFrame], threshold: float
) -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = []
    names = list(frames)
    for left_index, left_table in enumerate(names):
        for right_table in names[left_index + 1 :]:
            candidates: list[dict[str, Any]] = []
            for left_column in frames[left_table].columns:
                for right_column in frames[right_table].columns:
                    name_score = SequenceMatcher(
                        None, str(left_column).lower(), str(right_column).lower()
                    ).ratio()
                    value_score = _overlap(
                        frames[left_table][left_column], frames[right_table][right_column]
                    )
                    confidence = round((0.45 * name_score) + (0.55 * value_score), 3)
                    if confidence >= threshold:
                        candidates.append(
                            {
                                "left_table": left_table,
                                "left_column": str(left_column),
                                "right_table": right_table,
                                "right_column": str(right_column),
                                "confidence": confidence,
                            }
                        )
            hints.extend(sorted(candidates, key=lambda item: item["confidence"], reverse=True)[:3])
    return hints


def _parse_file(content: bytes, extension: str) -> dict[str, pd.DataFrame]:
    buffer = io.BytesIO(content)
    if extension == ".csv":
        return {"": pd.read_csv(buffer)}
    engine = "xlrd" if extension == ".xls" else "openpyxl"
    sheets = pd.read_excel(buffer, sheet_name=None, engine=engine)
    return {str(name): frame for name, frame in sheets.items()}


async def ingest_files(
    settings: Settings, files: Iterable[UploadFile]
) -> UploadResponse:
    uploads = list(files)
    if not uploads:
        raise UploadValidationError("Upload at least one CSV or Excel file")
    if len(uploads) > settings.upload.max_files:
        raise UploadValidationError(
            f"A maximum of {settings.upload.max_files} files is allowed"
        )

    session_id, directory = create_session(settings)
    frames: dict[str, pd.DataFrame] = {}
    sources: dict[str, str] = {}
    used_tables: set[str] = set()
    max_bytes = settings.upload.max_file_size_mb * 1024 * 1024

    for upload in uploads:
        filename = Path(upload.filename or "upload").name
        extension = Path(filename).suffix.lower()
        if extension not in settings.upload.allowed_extensions:
            raise UploadValidationError(f"Unsupported file type: {filename}")
        content = await upload.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise UploadValidationError(
                f"{filename} exceeds {settings.upload.max_file_size_mb} MB"
            )
        try:
            parsed = _parse_file(content, extension)
        except Exception as exc:
            raise UploadValidationError(f"Could not parse {filename}: {exc}") from exc
        for sheet, raw_frame in parsed.items():
            if raw_frame.empty and len(raw_frame.columns) == 0:
                continue
            base = safe_identifier(Path(filename).stem)
            if sheet:
                base = f"{base}_{safe_identifier(sheet, 'sheet')}"
            table = _unique_name(base, used_tables)
            frames[table] = _normalise_dataframe(raw_frame)
            sources[table] = filename if not sheet else f"{filename} / {sheet}"

    if not frames:
        raise UploadValidationError("No tabular data was found in the uploaded files")

    connection = duckdb.connect(str(directory / "data.duckdb"))
    try:
        for table, frame in frames.items():
            view_name = f"incoming_{table}"
            connection.register(view_name, frame)
            connection.execute(f'CREATE TABLE "{table}" AS SELECT * FROM "{view_name}"')
            connection.unregister(view_name)
    finally:
        connection.close()

    table_metadata = [
        {
            "name": table,
            "source": sources[table],
            "rows": len(frame),
            "columns": _profile(frame, settings.query.preview_rows),
        }
        for table, frame in frames.items()
    ]
    join_hints = infer_join_hints(frames, settings.query.join_hint_threshold)
    save_metadata(
        settings,
        session_id,
        {"tables": table_metadata, "join_hints": join_hints},
    )
    return UploadResponse(
        session_id=session_id,
        tables=[
            TableSummary(
                name=table["name"],
                source=table["source"],
                rows=table["rows"],
                columns=[column["name"] for column in table["columns"]],
            )
            for table in table_metadata
        ],
        join_hints=[JoinHint.model_validate(hint) for hint in join_hints],
    )
