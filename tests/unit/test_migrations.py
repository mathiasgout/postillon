import hashlib
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine, text

from postillon.db.models import Base
from postillon.db.session import _alembic_config, connect, migrate
from tests.support import MP4


def test_migrations_build_the_schema_of_the_models(engine: Engine):
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"render_as_batch": True})
        assert compare_metadata(context, Base.metadata) == []


def upgrade(engine: Engine, videos_dir: Path, revision: str) -> None:
    if revision == "head":
        migrate(engine, videos_dir)
        return
    with engine.begin() as connection:
        config = _alembic_config()
        config.attributes["connection"] = connection
        config.attributes["videos_dir"] = videos_dir
        command.upgrade(config, revision)


def insert(engine: Engine, entry_id: int, key: str, released: str | None) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO entries (id, project, key, publish_at, manifest, submitted_at, updated_at,"
                " video_released_at) VALUES (:id, 'my-project', :key, '2026-10-22 18:00:00', '{}',"
                " '2026-10-20 10:00:00', '2026-10-21 10:00:00', :released)"
            ),
            {"id": entry_id, "key": key, "released": released},
        )
        connection.execute(
            text(
                "INSERT INTO posts (entry_id, platform, account, content, status, failures, extra, updated_at,"
                " version) VALUES (:id, 'youtube', 'main', '{}', 'PENDING', 0, '{}', '2026-10-21 10:00:00', 1)"
            ),
            {"id": entry_id},
        )


@pytest.fixture
def old_engine(tmp_path: Path):
    engine = connect(tmp_path / "postillon.db")
    yield engine
    engine.dispose()


def test_keys_lose_their_segments_and_held_videos_their_old_name(old_engine: Engine, tmp_path: Path):
    videos = tmp_path / "videos"
    upgrade(old_engine, videos, "0001")
    insert(old_engine, 1, "season-1/day-23", None)
    insert(old_engine, 2, "season-1/day-1", "2026-10-21 18:00:00")
    held = videos / "my-project" / "season-1" / "day-23.mp4"
    held.parent.mkdir(parents=True)
    held.write_bytes(MP4)
    upgrade(old_engine, videos, "head")
    with old_engine.connect() as connection:
        rows = connection.execute(
            text("SELECT key, video_sha256, video_size, video_received_at, version FROM entries ORDER BY id")
        ).all()
        publish_at = connection.execute(text("SELECT publish_at FROM posts WHERE entry_id = 1")).scalar_one()
    sha256 = hashlib.sha256(MP4).hexdigest()
    assert [tuple(row) for row in rows] == [
        ("season-1-day-23", sha256, len(MP4), "2026-10-21 10:00:00", 1),
        ("season-1-day-1", None, None, None, 1),
    ]
    assert publish_at == "2026-10-22 18:00:00"
    with old_engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
    assert (videos / "my-project" / f"season-1-day-23.{sha256}.mp4").read_bytes() == MP4
    assert not (videos / "my-project" / "season-1").exists()


def test_a_renamed_key_taken_already_stops_the_migration(old_engine: Engine, tmp_path: Path):
    upgrade(old_engine, tmp_path / "videos", "0001")
    insert(old_engine, 1, "season-1-day-1", "2026-10-21 18:00:00")
    insert(old_engine, 2, "season-1/day-1", "2026-10-21 18:00:00")
    with pytest.raises(RuntimeError, match="season-1-day-1 exists already"):
        upgrade(old_engine, tmp_path / "videos", "head")
