"""The videos the service holds on its disk, from their reception until every platform has them
(see docs/statuses.md).

A video is received into a staging file, then moved into place under a name that carries its
SHA-256: a post being sent keeps reading the file it opened, and releasing one video never deletes
another of the same entry.
"""

from __future__ import annotations

import dataclasses
import hashlib
import os
import uuid
from pathlib import Path
from types import TracebackType

from postillon.errors import VideoNotMp4, VideoTooLarge
from postillon.storage.bucket import Bucket

# An MP4 file opens with a box whose type, at bytes 4 to 8, is `ftyp`.
MP4_SIGNATURE = b"ftyp"
SIGNATURE_END = 8


@dataclasses.dataclass(frozen=True)
class Staged:
    path: Path
    size: int
    sha256: str


class VideoStore:
    def __init__(self, root: Path, max_bytes: int):
        self.root = root
        self.max_bytes = max_bytes
        self._staging = root / ".staging"

    def path(self, project: str, key: str, sha256: str) -> Path:
        return self.root / project / f"{key}.{sha256}.mp4"

    def upload(self) -> Upload:
        """A staging file to write a received video into."""
        self._staging.mkdir(parents=True, exist_ok=True)
        return Upload(self._staging / f"{uuid.uuid4().hex}.mp4", self.max_bytes)

    def promote(self, staged: Staged, project: str, key: str) -> None:
        path = self.path(project, key, staged.sha256)
        path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staged.path, path)

    def discard(self, staged: Staged) -> None:
        staged.path.unlink(missing_ok=True)

    def delete(self, project: str, key: str, sha256: str) -> None:
        self.path(project, key, sha256).unlink(missing_ok=True)


class Upload:
    """A video being received; a refusal or an exception inside its `with` block removes the file."""

    def __init__(self, path: Path, max_bytes: int):
        self.path = path
        self.max_bytes = max_bytes
        self._file = path.open("wb")
        self._digest = hashlib.sha256()
        self._size = 0
        self._head = b""

    def write(self, chunk: bytes) -> None:
        """Appends a chunk; raises VideoTooLarge or VideoNotMp4 as soon as the bytes received show it."""
        self._size += len(chunk)
        if self._size > self.max_bytes:
            raise VideoTooLarge(f"video is over {self.max_bytes} bytes")
        if len(self._head) < SIGNATURE_END:
            self._head += chunk[: SIGNATURE_END - len(self._head)]
            if len(self._head) == SIGNATURE_END:
                self._check_signature()
        self._digest.update(chunk)
        self._file.write(chunk)

    def finish(self) -> Staged:
        """The received video; raises VideoNotMp4 when it is too short to be one."""
        self._file.close()
        if len(self._head) < SIGNATURE_END:
            raise VideoNotMp4("video is not an MP4 file")
        return Staged(self.path, self._size, self._digest.hexdigest())

    def _check_signature(self) -> None:
        if self._head[4:SIGNATURE_END] != MP4_SIGNATURE:
            raise VideoNotMp4("video is not an MP4 file")

    def __enter__(self) -> Upload:
        return self

    def __exit__(
        self, kind: type[BaseException] | None, error: BaseException | None, traceback: TracebackType | None
    ) -> None:
        if error is not None:
            self._file.close()
            self.path.unlink(missing_ok=True)


class StoredVideo:
    """The video of one entry as a platform reads it: a local file, or a signed URL of a copy in the bucket."""

    def __init__(self, videos: VideoStore, bucket: Bucket, project: str, key: str, sha256: str | None):
        self._videos = videos
        self._bucket = bucket
        self._project = project
        self._key = key
        self._sha256 = sha256

    def file(self) -> Path:
        return self._held()[0]

    def url(self, expires_seconds: int) -> str:
        path, sha256 = self._held()
        return self._bucket.video_url(self._project, self._key, path, sha256, expires_seconds)

    def _held(self) -> tuple[Path, str]:
        """The file of the video and its SHA-256; raises ValueError if the service no longer holds it."""
        if self._sha256 is None:
            raise ValueError(f"the service holds no video of {self._project}/{self._key}")
        path = self._videos.path(self._project, self._key, self._sha256)
        if not path.exists():
            raise ValueError(f"video {path} does not exist")
        return path, self._sha256
