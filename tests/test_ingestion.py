import pandas as pd

from app.services.ingestion import infer_join_hints, safe_identifier


def test_safe_identifier() -> None:
    assert safe_identifier("2025 Sales & Orders") == "t_2025_sales_orders"


def test_join_hints_use_names_and_value_overlap() -> None:
    frames = {
        "orders": pd.DataFrame({"customer_id": [1, 2, 3], "amount": [10, 20, 30]}),
        "customers": pd.DataFrame({"customer_id": [1, 2, 3], "name": ["A", "B", "C"]}),
    }
    hints = infer_join_hints(frames, threshold=0.5)
    best = hints[0]
    assert best["left_column"] == "customer_id"
    assert best["right_column"] == "customer_id"
    assert best["confidence"] == 1.0

