from __future__ import annotations

import json
from typing import Annotated

from langchain_core.tools import InjectedToolArg, tool

from app.core.config import Settings
from app.services.query_engine import execute_query


@tool("inspect_schema")
def inspect_schema_tool(
    metadata: Annotated[dict, InjectedToolArg],
    max_prompt_chars: Annotated[int, InjectedToolArg],
) -> str:
    """Inspect uploaded tables, columns, samples, and inferred join hints."""
    return json.dumps({"status": "schema_ready", "metadata": metadata}, default=str)[
        :max_prompt_chars
    ]


@tool("run_sql")
def run_sql_tool(
    sql: str,
    session_id: Annotated[str, InjectedToolArg],
    settings: Annotated[Settings, InjectedToolArg],
) -> str:
    """Run one read-only DuckDB SELECT query against the uploaded data."""
    try:
        safe_sql, columns, rows = execute_query(settings, session_id, sql)
        return json.dumps(
            {
                "status": "query_success",
                "sql": safe_sql,
                "columns": columns,
                "rows": rows,
            },
            default=str,
        )
    except Exception as exc:
        return json.dumps({"status": "query_error", "error": str(exc)})


AGENT_TOOLS = [inspect_schema_tool, run_sql_tool]
