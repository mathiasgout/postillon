"""The bodies the API returns (see docs/api.md); the manifest a producer sends is `postillon.manifest`."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, computed_field

from postillon.domain import Status
from postillon.platforms import POSTS


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: Status
    error: str | None
    at: datetime


class PostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    platform: str
    account: str
    status: Status
    remote_id: str | None
    error: str | None
    failures: int
    extra: dict[str, Any]
    updated_at: datetime
    events: list[EventOut]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def manual(self) -> bool:
        return POSTS[self.platform].manual


class EntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project: str
    key: str
    publish_at: datetime
    manifest: dict[str, Any]
    submitted_at: datetime
    updated_at: datetime
    video_released_at: datetime | None
    posts: list[PostOut]


class SubmissionOut(BaseModel):
    entry: EntryOut
    # Platforms whose post may have reached the platform, left as they were sent.
    ignored: list[str]
