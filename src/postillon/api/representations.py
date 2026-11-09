"""The representation of each resource the API serves, built from the database by one function per
resource, and the bodies it receives besides the manifest (see docs/api.md).

The database may change without changing these; the manifest a producer sends is `postillon.manifest`.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Annotated, Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, StringConstraints, ValidationError, field_validator

from postillon.db.models import Entry, Event, Post
from postillon.domain import SENT, Status
from postillon.manifest import EntryKey, Manifest
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
    """An entry published outside the service: its key, its manifest, and when each post went public."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: EntryKey
    manifest: Manifest
    published: dict[str, PublicationIn]


class VideoOut(BaseModel):
    size: int
    sha256: str
    received_at: datetime
    released_at: datetime | None


class PostOut(BaseModel):
    project: str
    key: str
    platform: str
    account: str
    manual: bool
    status: Status
    publish_at: datetime
    # The post may have reached its platform with a content or a time the latest manifest no longer has.
    outdated: bool
    remote_id: str | None
    error: str | None
    failures: int
    extra: dict[str, Any]
    updated_at: datetime


class EntryOut(BaseModel):
    project: str
    key: str
    publish_at: datetime
    manifest: dict[str, Any]
    submitted_at: datetime
    updated_at: datetime
    video: VideoOut | None
    posts: list[PostOut]


class EntryList(BaseModel):
    entries: list[EntryOut]
    next_page_token: str | None


class EventOut(BaseModel):
    project: str
    key: str
    platform: str
    status: Status
    error: str | None
    at: datetime


class EventList(BaseModel):
    events: list[EventOut]
    next_page_token: str | None


def entry_out(entry: Entry) -> EntryOut:
    video = None
    if entry.video_sha256 is not None and entry.video_size is not None and entry.video_received_at is not None:
        video = VideoOut(
            size=entry.video_size,
            sha256=entry.video_sha256,
            received_at=entry.video_received_at,
            released_at=entry.video_released_at,
        )
    return EntryOut(
        project=entry.project,
        key=entry.key,
        publish_at=entry.publish_at,
        manifest=entry.manifest,
        submitted_at=entry.submitted_at,
        updated_at=entry.updated_at,
        video=video,
        posts=[post_out(post, entry) for post in entry.posts],
    )


def post_out(post: Post, entry: Entry) -> PostOut:
    return PostOut(
        project=entry.project,
        key=entry.key,
        platform=post.platform,
        account=post.account,
        manual=PLATFORMS[post.platform].manual,
        status=post.status,
        publish_at=post.publish_at,
        outdated=_outdated(post, entry),
        remote_id=post.remote_id,
        error=post.error,
        failures=post.failures,
        extra=post.extra,
        updated_at=post.updated_at,
    )


def event_out(event: Event) -> EventOut:
    post = event.post
    return EventOut(
        project=post.entry.project,
        key=post.entry.key,
        platform=post.platform,
        status=event.status,
        error=event.error,
        at=event.at,
    )


def entry_etag(entry: Entry) -> str:
    """Changes with the entry and with each of its posts, which its representation embeds."""
    versions = ",".join(f"{post.platform}={post.version}" for post in entry.posts)
    return f'"{hashlib.sha256(f"{entry.version};{versions}".encode()).hexdigest()[:20]}"'


def post_etag(post: Post) -> str:
    """Changes with the post and with its entry, which decides whether the post is outdated."""
    return f'"{post.entry.version}-{post.version}"'


def video_etag(sha256: str) -> str:
    return f'"{sha256}"'


def _outdated(post: Post, entry: Entry) -> bool:
    if post.status not in SENT:
        return False
    current = entry.manifest["posts"].get(post.platform)
    if current is None or post.publish_at != entry.publish_at:
        return True
    try:
        content = PLATFORMS[post.platform].post.model_validate(current).model_dump(mode="json")
    except ValidationError:
        return True
    return content != post.content
