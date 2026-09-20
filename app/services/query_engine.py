from __future__ import annotations

import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import duckdb

from app.core.config import Settings
from app.services.session_store import get_database_path, load_metadata
from app.services.sql_guard import validate_and_limit_sql


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, (datetime, date, Decimal)):
        return str(value)
    if hasattr(value, "item"):
        return value.item()
    return value


def execute_query(
    settings: Settings, session_id: str, sql: str
) -> tuple[str, list[str], list[dict[str, Any]]]:
    metadata = load_metadata(settings, session_id)
    allowed_tables = {table["name"].lower() for table in metadata["tables"]}
    safe_sql = validate_and_limit_sql(sql, settings.query.row_limit, allowed_tables)
    connection = duckdb.connect(str(get_database_path(settings, session_id)), read_only=True)
    try:
        cursor = connection.execute(safe_sql)
        columns = [item[0] for item in cursor.description]
        rows = [
            {column: _json_value(value) for column, value in zip(columns, record, strict=True)}
            for record in cursor.fetchall()
        ]
    finally:
        connection.close()
    return safe_sql, columns, rows
