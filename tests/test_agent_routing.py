import json

from langchain_core.messages import AIMessage, ToolMessage

from app.agents.graph import SCHEMA_TOOL, SQL_TOOL, route_agent_tool
from app.agents.nodes import process_sql_output_node, schema_tool_node
from app.core.config import get_settings


def test_schema_route_injects_hidden_state_arguments() -> None:
    settings = get_settings()
    message = AIMessage(
        content="",
        tool_calls=[{"name": "inspect_schema", "args": {}, "id": "schema-1"}],
    )
    state = {"messages": [message], "metadata": {"tables": []}, "steps": 1}

    route = route_agent_tool(state, {"configurable": {"settings": settings}})

    assert route == SCHEMA_TOOL
    assert message.tool_calls[0]["args"]["metadata"] == {"tables": []}


def test_sql_route_injects_session_and_settings() -> None:
    settings = get_settings()
    message = AIMessage(
        content="",
        tool_calls=[{"name": "run_sql", "args": {"sql": "SELECT 1"}, "id": "sql-1"}],
    )
    state = {"messages": [message], "session_id": "session-123", "steps": 1}

    route = route_agent_tool(state, {"configurable": {"settings": settings}})

    assert route == SQL_TOOL
    assert message.tool_calls[0]["args"]["session_id"] == "session-123"
    assert message.tool_calls[0]["args"]["settings"] is settings


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
    message = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "inspect_schema",
                "args": {"metadata": {"tables": []}, "max_prompt_chars": 1000},
                "id": "schema-1",
            }
        ],
    )

    update = schema_tool_node({"messages": [message]})

    assert isinstance(update["messages"][0], ToolMessage)
    assert '"status": "schema_ready"' in update["messages"][0].content

