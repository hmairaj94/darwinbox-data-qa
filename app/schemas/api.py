from typing import Any, Literal

from pydantic import BaseModel, Field


class TableSummary(BaseModel):
    name: str
    source: str
    rows: int
    columns: list[str]


class JoinHint(BaseModel):
    left_table: str
    left_column: str
    right_table: str
    right_column: str
    confidence: float


class UploadResponse(BaseModel):
    session_id: str
    tables: list[TableSummary]
    join_hints: list[JoinHint]


class QueryRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)


class ChartSpec(BaseModel):
    type: Literal["bar", "line", "pie"]
    title: str
    x: str
    y: str


class QueryResponse(BaseModel):
    answer: str
    sql: str
    columns: list[str]
    rows: list[dict[str, Any]]
    chart: ChartSpec | None = None
    attempts: int

