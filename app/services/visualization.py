from __future__ import annotations

from numbers import Number
from typing import Any

from app.schemas.api import ChartSpec

VISUAL_WORDS = {"chart", "graph", "plot", "trend", "visual", "compare", "distribution"}


def suggest_chart(
    question: str, columns: list[str], rows: list[dict[str, Any]]
) -> ChartSpec | None:
    if not rows or len(columns) < 2 or len(rows) > 50:
        return None
    wants_chart = any(word in question.lower() for word in VISUAL_WORDS)
    numeric = [
        column
        for column in columns
        if any(isinstance(row.get(column), Number) for row in rows if row.get(column) is not None)
    ]
    categorical = [column for column in columns if column not in numeric]
    if not numeric or not categorical:
        return None
    x, y = categorical[0], numeric[0]
    is_time = any(token in x.lower() for token in ("date", "month", "year", "time"))
    if not wants_chart and not is_time:
        return None
    return ChartSpec(
        type="line" if is_time else "bar",
        title=question[:100],
        x=x,
        y=y,
    )
