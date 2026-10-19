"""The FastAPI application: its state, its routes under `/v1` and its health check (see docs/api.md)."""

from __future__ import annotations

from importlib.metadata import version

from fastapi import FastAPI

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

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
