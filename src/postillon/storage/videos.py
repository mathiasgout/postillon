"""The videos the service holds on its disk, from their submission until every platform has them
(see docs/statuses.md).

A video is staged, checked, then moved into place atomically, so that an upload in progress
keeps reading the file it opened when the entry is submitted again.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import BinaryIO

from postillon.errors import VideoNotMp4, VideoTooLarge
from postillon.storage.bucket import Bucket

CHUNK_BYTES = 1024 * 1024
# An MP4 file opens with a box whose type, at bytes 4 to 8, is `ftyp`.
MP4_SIGNATURE = b"ftyp"


class VideoStore:
    def __init__(self, root: Path, max_bytes: int):
        self.root = root
        self.max_bytes = max_bytes
        self._staging = root / ".staging"

    def path(self, project: str, key: str) -> Path:
        return self.root / project / f"{key}.mp4"

    def exists(self, project: str, key: str) -> bool:
        return self.path(project, key).exists()

    def stage(self, source: BinaryIO) -> Path:
        """Copies the video to a staging file; raises VideoTooLarge or VideoNotMp4."""
        self._staging.mkdir(parents=True, exist_ok=True)
        staged = self._staging / f"{uuid.uuid4().hex}.mp4"
        size = 0
        try:
            with staged.open("wb") as out:
                while chunk := source.read(CHUNK_BYTES):
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise VideoTooLarge(f"video is over {self.max_bytes} bytes")
                    out.write(chunk)
            with staged.open("rb") as f:
                if f.read(8)[4:8] != MP4_SIGNATURE:
                    raise VideoNotMp4("video is not an MP4 file")
        except BaseException:
            staged.unlink(missing_ok=True)
            raise
        return staged

    def promote(self, staged: Path, project: str, key: str) -> None:
        """Moves a staged video in place of the entry's previous one."""
        path = self.path(project, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staged, path)

    def discard(self, staged: Path) -> None:
        staged.unlink(missing_ok=True)

    def delete(self, project: str, key: str) -> None:
        self.path(project, key).unlink(missing_ok=True)


class StoredVideo:
    """The video of one entry as a platform reads it: a local file, or a signed URL of a copy in the bucket."""

    def __init__(self, videos: VideoStore, bucket: Bucket, project: str, key: str):
        self._videos = videos
        self._bucket = bucket
        self._project = project
        self._key = key

    def file(self) -> Path:
        path = self._videos.path(self._project, self._key)
        if not path.exists():
            raise ValueError(f"video {path} does not exist")
        return path

    def url(self, expires_seconds: int) -> str:
        return self._bucket.video_url(self._project, self._key, self.file(), expires_seconds)
