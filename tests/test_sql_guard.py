import pytest

from app.core.exceptions import UnsafeQueryError
from app.services.sql_guard import validate_and_limit_sql


def test_adds_configured_limit() -> None:
    result = validate_and_limit_sql(
        "SELECT region, sum(total) FROM orders GROUP BY region", 25, {"orders"}
    )
    assert "LIMIT 25" in result


def test_keeps_existing_limit() -> None:
    result = validate_and_limit_sql("SELECT * FROM orders LIMIT 3", 25, {"orders"})
    assert "LIMIT 3" in result
    assert "LIMIT 25" not in result


@pytest.mark.parametrize(
    "query",
    [
        "DROP TABLE orders",
        "SELECT * FROM secret_table",
        "SELECT * FROM information_schema.orders",
        "SELECT * FROM read_csv('/etc/passwd')",
        "SELECT * FROM orders; DELETE FROM orders",
    ],
)
def test_rejects_unsafe_queries(query: str) -> None:
    with pytest.raises(UnsafeQueryError):
        validate_and_limit_sql(query, 25, {"orders"})


def test_allows_cte_over_uploaded_table() -> None:
    result = validate_and_limit_sql(
        "WITH totals AS (SELECT region, sum(total) value FROM orders GROUP BY region) "
        "SELECT * FROM totals",
        25,
        {"orders"},
    )
    assert "totals" in result.lower()
