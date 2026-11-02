"""The contract between the service and a platform: the post a manifest carries, the task the
publisher hands over and the platform that performs it (see docs/add-a-platform.md).

Imports no platform SDK, so that the API validates a post without loading its platform.
"""

from __future__ import annotations

import dataclasses
import os
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated, ClassVar, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, StringConstraints

from postillon.domain import PostState

# A configuration key, scoped by project and platform.
AccountName = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_-]+$")]


class PlatformPost(BaseModel):
    """The publication of an entry on one platform, as the manifest carries it."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    name: ClassVar[str]
    # Scheduled by the operator, who tells the API once the platform holds the video.
    manual: ClassVar[bool] = False

    account: AccountName


class Video(Protocol):
    def file(self) -> Path:
        """The video as a local file; raises ValueError if the service no longer holds it."""
        ...

    def url(self, expires_seconds: int) -> str:
        """A signed URL the platform can fetch the video from until it expires."""
        ...


@dataclasses.dataclass(frozen=True)
class Task:
    post: PlatformPost
    publish_at: datetime
    state: PostState
    now: datetime
    video: Video
    # Records an intermediate state at once, such as `in_progress` before a long upload.
    checkpoint: Callable[[PostState], None]
    # The `publish_at` of the next entry with a post on the same platform and account.
    next_publish_at: datetime | None


class Platform(Protocol):
    def step(self, task: Task) -> PostState:
        """The post's new state after acting on the platform, if anything is due. An expected refusal
        returns `failed` or `rejected` with an error; any exception counts as `failed`."""
        ...


@runtime_checkable
class ChecksCredentials(Protocol):
    """A platform whose credentials expire; the worker calls it once a day."""

    def check_credentials(self, now: datetime) -> None:
        """Renews the credentials that are due, or warns before they expire; logs a failure and keeps
        the current ones."""
        ...


def read_secret(variable: str) -> str:
    """The value of an environment variable holding a platform secret; raises ValueError if it is unset."""
    value = os.environ.get(variable)
    if not value:
        raise ValueError(f"environment variable {variable} is not set")
    return value
