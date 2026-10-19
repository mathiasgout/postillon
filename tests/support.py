"""Constants and fakes shared by the tests."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

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

    def video_url(self, project: str, key: str, path: Path, expires_seconds: int) -> str:
        self.videos.add((project, key))
        return f"https://signed.example/{project}/{key}.mp4?expires={expires_seconds}"

    def delete_video(self, project: str, key: str) -> None:
        self.videos.discard((project, key))
        self.deleted.append((project, key))

    def upload_backup(self, path: Path, day: object) -> None:
        self.backups.append((path.read_bytes(), str(day)))
