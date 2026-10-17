"""The contract between the service and the adapter of a platform (see docs/add-a-platform.md).

The service hands each post that needs work to its platform's adapter as a `Task`; the
adapter acts on the platform and returns the post's new state.
"""

from __future__ import annotations

import dataclasses
import importlib
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from postillon.bucket import Bucket
from postillon.entry import Entry
from postillon.platforms.base import Post
from postillon.state import PostState


class Video:
    """The video of one entry, downloaded at most once per pass."""

    def __init__(self, bucket: Bucket, entry_id: str, workdir: Path):
        self._bucket = bucket
        self._entry_id = entry_id
        self._path = workdir / "video.mp4"

    def file(self) -> Path:
        """The video as a local file; raises ValueError if the bucket has none."""
        if not self._path.exists():
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._bucket.download_video(self._entry_id, self._path)
        return self._path

    def url(self, expires_seconds: int) -> str:
        """A signed URL a platform can fetch the video from until it expires."""
        return self._bucket.video_url(self._entry_id, expires_seconds)


@dataclasses.dataclass(frozen=True)
class Task:
    entry: Entry
    post: Post
    state: PostState
    now: datetime
    video: Video
    # Records an intermediate state at once, such as `in_progress` before a long upload.
    checkpoint: Callable[[PostState], None]


class Adapter(Protocol):
    def __init__(self, accounts: dict[str, dict[str, Any]]) -> None:
        """Takes the settings of the platform's accounts in one project; raises ValueError on invalid settings."""

    def step(self, task: Task) -> PostState:
        """The post's new state after acting on the platform, if anything is due."""


def load_adapter(platform: str, accounts: dict[str, dict[str, Any]]) -> Adapter:
    """The adapter of a platform, from the `Adapter` class of its `adapter` module; raises
    ValueError when the platform's extra is not installed."""
    try:
        module = importlib.import_module(f"postillon.platforms.{platform}.adapter")
    except ModuleNotFoundError as e:
        raise ValueError(f"{platform}: adapter unavailable ({e.name} missing), install postillon[{platform}]") from None
    return module.Adapter(accounts)
