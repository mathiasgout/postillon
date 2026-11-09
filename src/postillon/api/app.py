"""The FastAPI application: its state, its routes under `/v1`, its health check (see docs/api.md) and
the administration pages under `/admin/` (see docs/admin-page.md)."""

from __future__ import annotations

from importlib.metadata import version
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from postillon.api import problems
from postillon.api.routes import entries
from postillon.db.session import check_schema, connect, sessions
from postillon.settings import Settings
from postillon.storage.videos import VideoStore


def create_app(settings: Settings) -> FastAPI:
    """The application over the configured database; raises ValueError when its schema is not current."""
    engine = connect(settings.database)
    check_schema(engine)
    app = FastAPI(title="postillon", version=version("postillon"))
    app.state.settings = settings
    app.state.sessions = sessions(engine)
    app.state.videos = VideoStore(settings.videos_dir, settings.max_video_bytes)
    app.include_router(entries.router, prefix="/v1")
    problems.install(app)

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", include_in_schema=False)
    def home() -> RedirectResponse:
        return RedirectResponse("/admin/")

    app.mount("/admin", StaticFiles(directory=Path(__file__).parent.parent / "web", html=True), name="admin")
    return app
