"""Constants, fakes and helpers shared by the tests."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from postillon.db.models import Entry, Post
from postillon.services import entries, reception
from postillon.services.transaction import commit
from postillon.storage.videos import Staged, VideoStore

PUBLISH_AT = datetime(2026, 10, 22, 18, 0, tzinfo=UTC)
BEFORE = PUBLISH_AT - timedelta(days=1)
# The smallest file the service takes for an MP4: a box whose type is `ftyp`.
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64


class FakeBucket:
    """The bucket of `postillon.storage.bucket`, with its objects as a set of keys."""

    def __init__(self) -> None:
        self.videos: set[tuple[str, str]] = set()
        self.deleted: list[tuple[str, str]] = []
        self.backups: list[tuple[bytes, str]] = []

    def video_url(self, project: str, key: str, path: Path, sha256: str, expires_seconds: int) -> str:
        self.videos.add((project, key))
        return f"https://signed.example/{project}/{key}.mp4?expires={expires_seconds}"

    def delete_video(self, project: str, key: str) -> None:
        self.videos.discard((project, key))
        self.deleted.append((project, key))

    def upload_backup(self, path: Path, day: object) -> None:
        self.backups.append((path.read_bytes(), str(day)))


def stage(videos: VideoStore, content: bytes = MP4) -> Staged:
    with videos.upload() as upload:
        upload.write(content)
        return upload.finish()


def give_video(
    session_factory: sessionmaker[Session], videos: VideoStore, key: str, content: bytes = MP4, now: datetime = BEFORE
) -> Staged:
    """Records `content` as the video of the entry and puts it in place, as the API does."""
    staged = stage(videos, content)
    with session_factory() as session:
        entry = entries.get(session, "my-project", key)
        assert entry is not None
        reception.receive(entry, staged, now)
        commit(session)
    videos.promote(staged, "my-project", key)
    return staged


def posts(session_factory: sessionmaker[Session], key: str) -> dict[str, Post]:
    """The posts of the entry with their history, readable once the session is closed."""
    with session_factory() as session:
        found = session.scalars(
            select(Post).join(Post.entry).where(Entry.key == key).options(selectinload(Post.events))
        ).all()
        return {post.platform: post for post in found}
