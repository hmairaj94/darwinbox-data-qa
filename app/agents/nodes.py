from __future__ import annotations

import json

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_groq import ChatGroq

from app.agents.state import AgentState
from app.agents.tools import AGENT_TOOLS, inspect_schema_tool, run_sql_tool
from app.core.config import Settings

SYSTEM_PROMPT = """You are a careful data analyst working with uploaded tables in DuckDB.
Follow this tool contract exactly:
1. Call inspect_schema before writing SQL. Never invent a table, column, or join key.
2. Use the provided join hints for cross-file analysis. Prefer explicit JOIN conditions.
3. Call run_sql with exactly one read-only SELECT query using DuckDB syntax.
4. If a query fails, use the returned error to correct it. Never repeat the same SQL.
5. Never claim a numeric result without a successful run_sql result.
The system enforces a row limit and finite step and retry budgets."""


def _settings_from_config(config: RunnableConfig) -> Settings:
    settings = config.get("configurable", {}).get("settings")
    if not isinstance(settings, Settings):
        raise ValueError("Settings are required in the graph configuration")
    return settings


def create_chat_model(settings: Settings) -> ChatGroq:
    return ChatGroq(
        api_key=settings.groq_api_key,
        model=settings.model.name,
        temperature=settings.model.temperature,
        max_retries=settings.model.max_retries,
    )


def agent_node(state: AgentState, config: RunnableConfig) -> dict:
    """Choose the next tool from the conversation and its previous tool outputs."""
    settings = _settings_from_config(config)
    model = create_chat_model(settings).bind_tools(AGENT_TOOLS)
    messages = [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
    response = model.invoke(messages)
    steps = state.get("steps", 0) + 1
    if not response.tool_calls:
        return {
            "messages": [response],
            "steps": steps,
            "tool_outcome": "agent_error",
            "error": "The model did not execute a data query.",
        }
    return {"messages": [response], "steps": steps}


def _execute_requested_tool(
    state: AgentState, selected_tool, injected_args: dict | None = None
) -> dict:
    last_message = state["messages"][-1]
    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        raise ValueError("No tool call found in graph state")
    tool_call = last_message.tool_calls[0]
    tool_args = {**tool_call["args"], **(injected_args or {})}
    result = selected_tool.invoke(tool_args)
    return {
        "messages": [
            ToolMessage(
                content=str(result),
                name=tool_call["name"],
                tool_call_id=tool_call["id"],
            )
        ]
    }


def schema_tool_node(state: AgentState, config: RunnableConfig) -> dict:
    """Execute the schema tool after the router injects trusted metadata."""
    settings = _settings_from_config(config)
    return _execute_requested_tool(
        state,
        inspect_schema_tool,
        {
            "metadata": state["metadata"],
            "max_prompt_chars": settings.query.max_prompt_chars,
        },
    )


def sql_tool_node(state: AgentState, config: RunnableConfig) -> dict:
    """Execute the SQL tool after the router injects session dependencies."""
    settings = _settings_from_config(config)
    return _execute_requested_tool(
        state,
        run_sql_tool,
        {"session_id": state["session_id"], "settings": settings},
    )


def process_sql_output_node(state: AgentState) -> dict:
    """Convert the SQL tool's JSON output into explicit graph state."""
    last_message = state["messages"][-1]
    if not isinstance(last_message, ToolMessage):
        return {"tool_outcome": "query_error", "error": "SQL tool output is missing"}
    attempts = state.get("attempts", 0) + 1
    try:
        payload = json.loads(str(last_message.content))
    except json.JSONDecodeError:
        return {
            "attempts": attempts,
            "tool_outcome": "query_error",
            "error": "SQL tool returned an invalid response",
        }
    if payload.get("status") != "query_success":
        return {
            "attempts": attempts,
            "tool_outcome": "query_error",
            "error": payload.get("error", "SQL execution failed"),
        }
    return {
        "attempts": attempts,
        "tool_outcome": "query_success",
        "sql": payload["sql"],
        "columns": payload["columns"],
        "rows": payload["rows"],
        "error": "",
    }


def synthesise_node(state: AgentState, config: RunnableConfig) -> dict:
    """Create the concise natural-language answer from a successful query result."""
    settings = _settings_from_config(config)
    result = json.dumps(
        {"columns": state.get("columns", []), "rows": state.get("rows", [])},
        default=str,
    )
    prompt = (
        "Answer the user's question using only this query result. Be concise, mention key "
        "numbers, and say when the result is empty. Do not mention internal tools.\n\n"
        f"Question: {state['question']}\nSQL: {state.get('sql', '')}\nResult: {result}"
    )
    response = create_chat_model(settings).invoke(prompt)
    return {"answer": str(response.content)}
