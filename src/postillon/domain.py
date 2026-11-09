"""The statuses of a post, who may change them, and the state a platform reads and returns (see
docs/statuses.md).

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


class Actor(StrEnum):
    """Who changes the status of a post."""

    PRODUCER = "producer"
    WORKER = "worker"
    OPERATOR = "operator"


# The statuses whose post the worker still steps.
ACTIVE = frozenset({Status.PENDING, Status.IN_PROGRESS, Status.FAILED, Status.SCHEDULED})
# The platform holds the video: the service no longer needs its copy.
HOLDS_VIDEO = frozenset({Status.SCHEDULED, Status.PUBLISHED})
# Something may have reached the platform: a new submission no longer changes the post.
SENT = frozenset({Status.IN_PROGRESS, Status.SCHEDULED, Status.PUBLISHED})


# The status changes each actor may make; None stands for a post that does not exist yet.
TRANSITIONS: frozenset[tuple[Actor, Status | None, Status]] = frozenset(
    {
        # A submission creates a post, and gives a rejected one another try.
        (Actor.PRODUCER, None, Status.PENDING),
        (Actor.PRODUCER, Status.REJECTED, Status.PENDING),
        # A record creates a post published outside the service.
        (Actor.PRODUCER, None, Status.PUBLISHED),
        # The operator schedules a post on a manual platform.
        (Actor.OPERATOR, Status.PENDING, Status.SCHEDULED),
        # The worker takes whatever status the platform returns for a post it steps.
        *((Actor.WORKER, current, new) for current in ACTIVE for new in Status if new != current),
    }
)


def allowed(actor: Actor, current: Status | None, new: Status) -> bool:
    return (actor, current, new) in TRANSITIONS


@dataclasses.dataclass(frozen=True)
class PostState:
    status: Status = Status.PENDING
    remote_id: str | None = None
    error: str | None = None
    # Fields a platform keeps between two steps of its post, described by the platform's document.
    extra: dict[str, Any] = dataclasses.field(default_factory=dict)
