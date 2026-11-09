"""The manifest of an entry: its publication time and its posts, the JSON a producer submits
(see docs/manifest.md).

Only module that reads a manifest; `Posts` takes its fields from the platform registry.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    StringConstraints,
    create_model,
    field_validator,
    model_validator,
)

from postillon.platforms import PLATFORMS
from postillon.platforms.base import PlatformPost

# Chosen by the producer, unique within its project and never reused; `/` groups entries.
EntryKey = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_-]+(/[a-z0-9_-]+)*$", max_length=200)]


class _Posts(BaseModel):
    """One post per platform the entry is published on."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    def by_platform(self) -> dict[str, PlatformPost]:
        return {name: post for name in PLATFORMS if (post := getattr(self, name)) is not None}


# A field per platform of the registry; type checkers see its base, which declares every method.
if TYPE_CHECKING:
    Posts = _Posts
else:
    Posts = create_model(
        "Posts",
        __base__=_Posts,
        __doc__=_Posts.__doc__,
        **{name: (spec.post | None, None) for name, spec in PLATFORMS.items()},
    )


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
