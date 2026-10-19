"""The statuses of a post and the state a platform reads and returns (see docs/statuses.md).

Shared by the database, the services and the platforms; it depends on none of them.
"""

from __future__ import annotations

import dataclasses
from enum import StrEnum
from typing import Any


class Status(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    FAILED = "failed"
    REJECTED = "rejected"


# The platform holds the video: the service no longer needs its copy.
HOLDS_VIDEO = frozenset({Status.SCHEDULED, Status.PUBLISHED})
# Something may have reached the platform: a new submission no longer changes the post.
SENT = frozenset({Status.IN_PROGRESS, Status.SCHEDULED, Status.PUBLISHED})


@dataclasses.dataclass(frozen=True)
class PostState:
    status: Status = Status.PENDING
    remote_id: str | None = None
    error: str | None = None
    # Fields a platform keeps between two steps of its post, described by the platform's document.
    extra: dict[str, Any] = dataclasses.field(default_factory=dict)
