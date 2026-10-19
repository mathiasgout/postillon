"""The manifest of an entry: its publication time and its posts, the JSON a producer submits
(see docs/manifest.md).

Only module that reads a manifest; adding a platform adds a field to `Posts`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, StringConstraints, field_validator, model_validator

from postillon.platforms import POSTS
from postillon.platforms.base import PlatformPost
from postillon.platforms.instagram import InstagramPost
from postillon.platforms.tiktok import TikTokPost
from postillon.platforms.youtube import YouTubePost

# Chosen by the producer, unique within its project and never reused; `/` groups entries.
EntryKey = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_-]+(/[a-z0-9_-]+)*$", max_length=200)]


class Posts(BaseModel):
    """One post per platform the entry is published on."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    youtube: YouTubePost | None = None
    instagram: InstagramPost | None = None
    tiktok: TikTokPost | None = None

    def by_platform(self) -> dict[str, PlatformPost]:
        return {name: post for name in POSTS if (post := getattr(self, name)) is not None}


class Manifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    publish_at: AwareDatetime
    posts: Posts

    @field_validator("publish_at")
    @classmethod
    def _in_utc(cls, publish_at: datetime) -> datetime:
        return publish_at.astimezone(UTC)

    @model_validator(mode="after")
    def _has_a_post(self) -> Manifest:
        if not self.posts.by_platform():
            raise ValueError("the entry has no post")
        return self
