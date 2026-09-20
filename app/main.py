from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.error_handlers import register_error_handlers
from app.core.logger_setup import configure_logging
from app.routers.api import router

settings = get_settings()
configure_logging(settings.app.debug)


app = FastAPI(title=settings.app.name)
register_error_handlers(app)
app.include_router(router)

frontend = Path(__file__).parent / "frontend"
app.mount("/static", StaticFiles(directory=frontend), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(frontend / "index.html")
