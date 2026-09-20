import asyncio
import io

import pandas as pd
from fastapi import UploadFile

from app.core.config import load_settings
from app.services.excel_detection import detect_sheet_tables
from app.services.ingestion import infer_join_hints, ingest_files, safe_identifier


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


def test_detects_header_below_title_row() -> None:
    raw = pd.DataFrame(
        [
            ["Quarterly sales report", None, None],
            ["Region", "Revenue", "Units"],
            ["North", 100, 4],
            ["South", 80, 3],
        ]
    )

    tables = detect_sheet_tables(raw)

    assert len(tables) == 1
    assert tables[0]["frame"].columns.tolist() == ["Region", "Revenue", "Units"]
    assert tables[0]["source_range"] == "A2:C4"
    assert "Ignored 1 leading row(s)" in tables[0]["warnings"][0]


def test_flattens_merged_style_multirow_header() -> None:
    raw = pd.DataFrame(
        [
            ["Region", "Revenue", None],
            [None, "Q1", "Q2"],
            ["North", 100, 120],
            ["South", 80, 90],
        ]
    )

    tables = detect_sheet_tables(raw)

    assert len(tables) == 1
    assert tables[0]["frame"].columns.tolist() == [
        "Region",
        "Revenue_Q1",
        "Revenue_Q2",
    ]
    assert "Flattened a multi-row header." in tables[0]["warnings"]


def test_splits_multiple_vertical_tables() -> None:
    raw = pd.DataFrame(
        [
            ["Region", "Revenue"],
            ["North", 100],
            ["South", 80],
            [None, None],
            ["Product", "Units"],
            ["A", 4],
            ["B", 3],
        ]
    )

    tables = detect_sheet_tables(raw)

    assert len(tables) == 2
    assert tables[0]["frame"].columns.tolist() == ["Region", "Revenue"]
    assert tables[1]["frame"].columns.tolist() == ["Product", "Units"]
    assert all(
        "Multiple table regions were detected in this sheet." in table["warnings"]
        for table in tables
    )


def test_ingests_detected_excel_table(tmp_path) -> None:
    workbook = io.BytesIO()
    raw = pd.DataFrame(
        [
            ["Quarterly sales", None],
            ["Region", "Revenue"],
            ["North", 100],
            ["South", 80],
        ]
    )
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        raw.to_excel(writer, sheet_name="Summary", header=False, index=False)
    workbook.seek(0)
    settings = load_settings().model_copy(deep=True)
    settings.upload.data_dir = tmp_path
    upload = UploadFile(filename="messy.xlsx", file=workbook)

    response = asyncio.run(ingest_files(settings, [upload]))

    assert len(response.tables) == 1
    assert response.tables[0].name == "messy_summary"
    assert response.tables[0].columns == ["region", "revenue"]
    assert response.tables[0].source_range == "A2:B4"
    assert response.tables[0].warnings
