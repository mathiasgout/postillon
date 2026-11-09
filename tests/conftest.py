from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from postillon.db.session import connect, migrate, sessions
from postillon.settings import Settings
from postillon.storage.videos import VideoStore
from tests.support import FakeBucket


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        max_video_bytes=10_000,
        bucket={"endpoint": "https://r2.example", "access_key_id": "id", "secret_access_key": "secret", "name": "b"},
        projects={
            "my-project": {
                "youtube": {"main": {"handle": "@mychannel", "refresh_token_env": "MY_YOUTUBE_TOKEN"}},
                "instagram": {"main": {"username": "mychannel", "access_token_env": "MY_INSTAGRAM_TOKEN"}},
                "tiktok": {"main": {"handle": "@mychannel"}},
            },
        },
    )


@pytest.fixture
def engine(settings: Settings) -> Iterator[Engine]:
    engine = connect(settings.database)
    migrate(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessions(engine)


@pytest.fixture
def videos(settings: Settings) -> VideoStore:
    return VideoStore(settings.videos_dir, settings.max_video_bytes)


@pytest.fixture
def bucket() -> FakeBucket:
    return FakeBucket()
