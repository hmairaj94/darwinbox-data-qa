from app.services.visualization import suggest_chart


def test_suggests_bar_chart_for_comparison() -> None:
    chart = suggest_chart(
        "Compare revenue by region",
        ["region", "revenue"],
        [{"region": "North", "revenue": 10}, {"region": "South", "revenue": 20}],
    )
    assert chart is not None
    assert chart.type == "bar"
    assert chart.x == "region"
    assert chart.y == "revenue"


def test_does_not_force_chart_for_scalar_answer() -> None:
    assert suggest_chart("What is total revenue?", ["revenue"], [{"revenue": 30}]) is None
