"""The state the service keeps per entry (see docs/state.md).

Only module that converts between states and their JSON; the service is its only user.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime
from enum import StrEnum
from typing import Any, Self

STATE_VERSION = 1


class Status(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    FAILED = "failed"
    REJECTED = "rejected"


@dataclasses.dataclass(frozen=True)
class PostState:
    status: Status = Status.PENDING
    manifest_sha256: str | None = None
    remote_id: str | None = None
    updated_at: datetime | None = None
    error: str | None = None
    # Fields a platform adds to the state of its post, described by the platform's document.
    extra: dict[str, Any] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": str(self.status),
            "manifest_sha256": self.manifest_sha256,
            "remote_id": self.remote_id,
            "updated_at": _rfc3339(self.updated_at),
            "error": self.error,
            **self.extra,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        known = {f.name for f in dataclasses.fields(cls)} - {"extra"}
        updated_at = data.get("updated_at")
        return cls(
            status=Status(data["status"]),
            manifest_sha256=data.get("manifest_sha256"),
            remote_id=data.get("remote_id"),
            updated_at=datetime.fromisoformat(updated_at) if updated_at else None,
            error=data.get("error"),
            extra={k: v for k, v in data.items() if k not in known},
        )


@dataclasses.dataclass
class EntryState:
    manifest_sha256: str | None = None
    error: str | None = None
    posts: dict[str, PostState] = dataclasses.field(default_factory=dict)

    def to_json(self) -> bytes:
        data = {
            "version": STATE_VERSION,
            "manifest_sha256": self.manifest_sha256,
            "error": self.error,
            "posts": {name: post.to_dict() for name, post in self.posts.items()},
        }
        return json.dumps(data, indent=2, ensure_ascii=False).encode()

    @classmethod
    def from_json(cls, raw: bytes) -> Self:
        data = json.loads(raw)
        return cls(
            manifest_sha256=data.get("manifest_sha256"),
            error=data.get("error"),
            posts={name: PostState.from_dict(post) for name, post in data.get("posts", {}).items()},
        )


def _rfc3339(when: datetime | None) -> str | None:
    return when.strftime("%Y-%m-%dT%H:%M:%SZ") if when else None
