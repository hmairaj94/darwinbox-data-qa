import json

from langchain_core.messages import AIMessage, ToolMessage

from app.agents.graph import SCHEMA_TOOL, SQL_TOOL, route_agent_tool
from app.agents.nodes import process_sql_output_node, schema_tool_node, sql_tool_node
from app.agents.tools import run_sql_tool
from app.core.config import get_settings


def test_schema_route_does_not_mutate_message_arguments() -> None:
    settings = get_settings()
    message = AIMessage(
        content="",
        tool_calls=[{"name": "inspect_schema", "args": {}, "id": "schema-1"}],
    )
    state = {"messages": [message], "metadata": {"tables": []}, "steps": 1}

    route = route_agent_tool(state, {"configurable": {"settings": settings}})

    assert route == SCHEMA_TOOL
    assert message.tool_calls[0]["args"] == {}


def test_sql_route_keeps_settings_out_of_message_history() -> None:
    settings = get_settings()
    message = AIMessage(
        content="",
        tool_calls=[{"name": "run_sql", "args": {"sql": "SELECT 1"}, "id": "sql-1"}],
    )
    state = {"messages": [message], "session_id": "session-123", "steps": 1}

    route = route_agent_tool(state, {"configurable": {"settings": settings}})

    assert route == SQL_TOOL
    assert message.tool_calls[0]["args"] == {"sql": "SELECT 1"}


def test_sql_post_processor_updates_graph_state() -> None:
    payload = {
        "status": "query_success",
        "sql": "SELECT 1 AS total",
        "columns": ["total"],
        "rows": [{"total": 1}],
    }
    message = ToolMessage(content=json.dumps(payload), tool_call_id="sql-1")

    update = process_sql_output_node({"messages": [message], "attempts": 0})

    assert update["tool_outcome"] == "query_success"
    assert update["rows"] == [{"total": 1}]
    assert update["attempts"] == 1


def test_schema_tool_node_executes_injected_arguments() -> None:
    settings = get_settings()
    message = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "inspect_schema",
                "args": {},
                "id": "schema-1",
            }
        ],
    )

    update = schema_tool_node(
        {"messages": [message], "metadata": {"tables": []}},
        {"configurable": {"settings": settings}},
    )

    assert isinstance(update["messages"][0], ToolMessage)
    assert '"status": "schema_ready"' in update["messages"][0].content
    assert message.tool_calls[0]["args"] == {}


def test_sql_tool_injects_dependencies_without_mutating_history(monkeypatch) -> None:
    settings = get_settings()
    captured_args = {}

    def fake_invoke(_tool, args, **_kwargs):
        captured_args.update(args)
        return json.dumps(
            {
                "status": "query_error",
                "error": "deliberate retry test",
            }
        )

    monkeypatch.setattr(type(run_sql_tool), "invoke", fake_invoke)
    message = AIMessage(
        content="",
        tool_calls=[{"name": "run_sql", "args": {"sql": "bad sql"}, "id": "sql-1"}],
    )

    update = sql_tool_node(
        {"messages": [message], "session_id": "session-123"},
        {"configurable": {"settings": settings}},
    )

    assert captured_args["session_id"] == "session-123"
    assert captured_args["settings"] is settings
    assert message.tool_calls[0]["args"] == {"sql": "bad sql"}
    assert "deliberate retry test" in update["messages"][0].content
