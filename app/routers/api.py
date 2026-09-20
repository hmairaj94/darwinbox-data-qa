from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings, get_settings
from app.schemas.api import QueryRequest, QueryResponse, UploadResponse
from app.services.ingestion import ingest_files
from app.services.qa_service import answer_question

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/upload_file", response_model=UploadResponse)
async def create_session(
    files: Annotated[list[UploadFile], File()],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UploadResponse:
    return await ingest_files(settings, files)


@router.post("/sessions/{session_id}/query", response_model=QueryResponse)
async def query_session(
    session_id: str,
    request: QueryRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> QueryResponse:
    return await run_in_threadpool(answer_question, settings, session_id, request.question)
