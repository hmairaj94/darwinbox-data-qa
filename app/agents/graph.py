from __future__ import annotations

from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.nodes import (
    agent_node,
    process_sql_output_node,
    schema_tool_node,
    sql_tool_node,
    synthesise_node,
)
from app.agents.state import AgentState
from app.agents.tools import inspect_schema_tool, run_sql_tool
from app.core.config import Settings

AGENT = "agent"
SCHEMA_TOOL = "schema_tool"
SQL_TOOL = "sql_tool"
PROCESS_SQL_OUTPUT = "process_sql_output"
SYNTHESISE = "synthesise"


def route_agent_tool(
    state: AgentState, config: RunnableConfig
) -> Literal["schema_tool", "sql_tool", "end"]:
    """Route by tool name without mutating the persisted model message."""
    last_message = state["messages"][-1]
    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return "end"

    tool_call = last_message.tool_calls[0]
    settings = config.get("configurable", {}).get("settings")
    if not isinstance(settings, Settings):
        raise ValueError("Settings are required in the graph configuration")
    if state.get("steps", 0) >= settings.query.max_agent_steps:
        return "end"
    if tool_call["name"] == inspect_schema_tool.name:
        return SCHEMA_TOOL
    if tool_call["name"] == run_sql_tool.name:
        return SQL_TOOL
    return "end"


def route_sql_output(
    state: AgentState, config: RunnableConfig
) -> Literal["agent", "synthesise", "end"]:
    outcome = state.get("tool_outcome")
    if outcome == "query_success":
        return SYNTHESISE
    settings = config.get("configurable", {}).get("settings")
    if not isinstance(settings, Settings):
        raise ValueError("Settings are required in the graph configuration")
    if state.get("steps", 0) >= settings.query.max_agent_steps:
        return "end"
    if state.get("attempts", 0) >= settings.query.max_agent_attempts:
        return "end"
    return AGENT


def build_agent_graph() -> CompiledStateGraph:
    """Build the function-based data Q&A graph."""
    workflow = StateGraph(AgentState)
    workflow.add_node(AGENT, agent_node)
    workflow.add_node(SCHEMA_TOOL, schema_tool_node)
    workflow.add_node(SQL_TOOL, sql_tool_node)
    workflow.add_node(PROCESS_SQL_OUTPUT, process_sql_output_node)
    workflow.add_node(SYNTHESISE, synthesise_node)

    workflow.add_edge(START, AGENT)
    workflow.add_conditional_edges(
        AGENT,
        route_agent_tool,
        {SCHEMA_TOOL: SCHEMA_TOOL, SQL_TOOL: SQL_TOOL, "end": END},
    )
    workflow.add_edge(SCHEMA_TOOL, AGENT)
    workflow.add_edge(SQL_TOOL, PROCESS_SQL_OUTPUT)
    workflow.add_conditional_edges(
        PROCESS_SQL_OUTPUT,
        route_sql_output,
        {AGENT: AGENT, SYNTHESISE: SYNTHESISE, "end": END},
    )
    workflow.add_edge(SYNTHESISE, END)
    return workflow.compile()


def run_agent(
    settings: Settings, session_id: str, question: str, metadata: dict
) -> AgentState:
    initial: AgentState = {
        "messages": [HumanMessage(content=question)],
        "session_id": session_id,
        "question": question,
        "metadata": metadata,
        "attempts": 0,
        "steps": 0,
        "columns": [],
        "rows": [],
        "sql": "",
        "answer": "",
        "error": "",
    }
    config: RunnableConfig = {
        "configurable": {"settings": settings},
        "recursion_limit": (settings.query.max_agent_steps * 2) + 4,
    }
    return build_agent_graph().invoke(initial, config)
