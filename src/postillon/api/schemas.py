"""The bodies the API returns and the record it receives (see docs/api.md); the manifest a producer
sends is `postillon.manifest`."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, StringConstraints, computed_field, field_validator

from postillon.domain import Status
from postillon.manifest import Manifest
from postillon.platforms import PLATFORMS


class PublicationIn(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    at: AwareDatetime
    remote_id: Annotated[str, StringConstraints(min_length=1, max_length=200)] | None = None

    @field_validator("at")
    @classmethod
    def _in_utc(cls, at: datetime) -> datetime:
        return at.astimezone(UTC)


class RecordIn(BaseModel):
    """An entry published outside the service: its manifest, and when each post went public."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    manifest: Manifest
    published: dict[str, PublicationIn]


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
        return PLATFORMS[self.platform].manual


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
