from __future__ import annotations

import re

import sqlglot
from sqlglot import exp

from app.core.exceptions import UnsafeQueryError

BLOCKED_FUNCTIONS = {
    "read_csv",
    "read_csv_auto",
    "read_json",
    "read_parquet",
    "sqlite_scan",
    "postgres_scan",
    "httpfs",
}


def validate_and_limit_sql(sql: str, row_limit: int, allowed_tables: set[str]) -> str:
    cleaned = re.sub(r"^```(?:sql)?\s*|\s*```$", "", sql.strip(), flags=re.IGNORECASE)
    try:
        statements = sqlglot.parse(cleaned, read="duckdb")
    except sqlglot.errors.ParseError as exc:
        raise UnsafeQueryError(f"Invalid SQL: {exc}") from exc
    if len(statements) != 1 or statements[0] is None:
        raise UnsafeQueryError("Exactly one SQL statement is allowed")
    statement = statements[0]
    if not isinstance(statement, exp.Query):
        raise UnsafeQueryError("Only read-only SELECT queries are allowed")
    cte_names = {cte.alias_or_name.lower() for cte in statement.find_all(exp.CTE)}
    for table in statement.find_all(exp.Table):
        table_name = table.name.lower()
        is_qualified = bool(table.db or table.catalog)
        is_allowed = table_name in allowed_tables or table_name in cte_names
        if not table_name or is_qualified or not is_allowed:
            raise UnsafeQueryError(f"Table {table_name or '(table function)'} is not allowed")
    for function in statement.find_all(exp.Func):
        if function.sql_name().lower() in BLOCKED_FUNCTIONS:
            raise UnsafeQueryError(f"Function {function.sql_name()} is not allowed")
    if statement.args.get("limit") is None:
        statement = statement.limit(row_limit)
    return statement.sql(dialect="duckdb")
