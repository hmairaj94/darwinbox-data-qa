from app.agents.graph import run_agent
from app.core.config import Settings
from app.core.exceptions import AppError, ModelConfigurationError
from app.schemas.api import QueryResponse
from app.services.session_store import load_metadata
from app.services.visualization import suggest_chart


def answer_question(
    settings: Settings, session_id: str, question: str
) -> QueryResponse:
    if not settings.groq_api_key:
        raise ModelConfigurationError("GROQ_API_KEY is not configured")
    metadata = load_metadata(settings, session_id)
    state = run_agent(settings, session_id, question, metadata)
    if state.get("tool_outcome") != "query_success":
        detail = state.get("error") or "The agent could not produce a valid query"
        raise AppError(detail)
    columns = state.get("columns", [])
    rows = state.get("rows", [])
    return QueryResponse(
        answer=state.get("answer") or "The query completed successfully.",
        sql=state.get("sql", ""),
        columns=columns,
        rows=rows,
        chart=suggest_chart(question, columns, rows),
        attempts=state.get("attempts", 0),
    )
