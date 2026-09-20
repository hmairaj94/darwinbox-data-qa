from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    session_id: str
    question: str
    metadata: dict[str, Any]
    attempts: int
    steps: int
    tool_outcome: Literal["schema_ready", "query_success", "query_error", "agent_error"]
    sql: str
    columns: list[str]
    rows: list[dict[str, Any]]
    answer: str
    error: str
