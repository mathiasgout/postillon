"""The tables of the service: the submitted entries, their posts and the history of the posts'
statuses (see docs/statuses.md).

Changing a model takes a migration in `postillon/db/migrations/versions`, which imports nothing
from here: a migration describes the schema at its revision and never changes afterwards.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, TypeDecorator, UniqueConstraint
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from postillon.domain import Actor, Status, allowed
from postillon.errors import TransitionRefused


class UTCDateTime(TypeDecorator[datetime]):
    """A datetime stored in UTC and read back aware, which SQLite does not keep by itself."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return value.replace(tzinfo=UTC) if value is not None else None


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {datetime: UTCDateTime, dict[str, Any]: JSON}


class Entry(Base):
    __tablename__ = "entries"
    __table_args__ = (UniqueConstraint("project", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project: Mapped[str] = mapped_column(String(100))
    key: Mapped[str] = mapped_column(String(200))
    publish_at: Mapped[datetime] = mapped_column(index=True)
    # The latest manifest submitted, as received.
    manifest: Mapped[dict[str, Any]]
    submitted_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    # Set once every platform holds the video and the service deleted its copies.
    video_released_at: Mapped[datetime | None]

    posts: Mapped[list[Post]] = relationship(
        back_populates="entry",
        cascade="all, delete-orphan",
        order_by="Post.platform",
    )


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (UniqueConstraint("entry_id", "platform"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("entries.id", ondelete="CASCADE"))
    platform: Mapped[str] = mapped_column(String(50))
    account: Mapped[str] = mapped_column(String(100))
    # The platform's fields of the post, as its model in `postillon.platforms` validates them.
    content: Mapped[dict[str, Any]]
    status: Mapped[Status] = mapped_column(Enum(Status, native_enum=False, length=20), index=True)
    remote_id: Mapped[str | None] = mapped_column(String(200))
    error: Mapped[str | None]
    # Consecutive `failed` outcomes, which space out the retries.
    failures: Mapped[int] = mapped_column(default=0)
    extra: Mapped[dict[str, Any]] = mapped_column(default=dict)
    updated_at: Mapped[datetime]
    # Bumped on every write: the API and the worker never overwrite each other's change.
    version: Mapped[int] = mapped_column(default=1)

    entry: Mapped[Entry] = relationship(back_populates="posts")
    events: Mapped[list[Event]] = relationship(
        back_populates="post",
        cascade="all, delete-orphan",
        order_by="Event.id",
    )

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012 (read by the mapper, never mutated)

    @classmethod
    def new(
        cls,
        *,
        platform: str,
        account: str,
        content: dict[str, Any],
        status: Status,
        actor: Actor,
        now: datetime,
        since: datetime | None = None,
        remote_id: str | None = None,
    ) -> Post:
        """A post created in `status`, its first event at `since` (`now` by default); raises
        TransitionRefused when `actor` may not create a post in this status."""
        if not allowed(actor, None, status):
            raise TransitionRefused(f"the {actor} cannot create a {platform} post {status}")
        return cls(
            platform=platform,
            account=account,
            content=content,
            status=status,
            remote_id=remote_id,
            failures=0,
            extra={},
            updated_at=now,
            events=[Event(status=status, at=since or now)],
        )

    def move(
        self, status: Status, actor: Actor, now: datetime, error: str | None = None, *, dated: bool = True
    ) -> None:
        """Changes the status, with an event unless `dated` is false; raises TransitionRefused, having
        changed nothing, when `actor` may not make the change."""
        if not allowed(actor, self.status, status):
            raise TransitionRefused(f"the {self.platform} post is {self.status}: the {actor} cannot make it {status}")
        self.status = status
        self.error = error
        self.updated_at = now
        if dated:
            self.events.append(Event(status=status, error=error, at=now))


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), index=True)
    status: Mapped[Status] = mapped_column(Enum(Status, native_enum=False, length=20))
    error: Mapped[str | None]
    at: Mapped[datetime]

    post: Mapped[Post] = relationship(back_populates="events")
