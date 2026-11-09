"""What the routes receive by injection, built once by `create_app` and kept on the app's state."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session, sessionmaker

from postillon.settings import Settings
from postillon.storage.videos import VideoStore


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def _session(request: Request) -> Iterator[Session]:
    with request.app.state.sessions() as session:
        yield session


def _sessions(request: Request) -> sessionmaker[Session]:
    """For an async route, which opens its sessions in the thread pool."""
    sessions: sessionmaker[Session] = request.app.state.sessions
    return sessions


def _videos(request: Request) -> VideoStore:
    videos: VideoStore = request.app.state.videos
    return videos


SettingsDep = Annotated[Settings, Depends(_settings)]
SessionDep = Annotated[Session, Depends(_session)]
SessionsDep = Annotated[sessionmaker[Session], Depends(_sessions)]
VideosDep = Annotated[VideoStore, Depends(_videos)]
