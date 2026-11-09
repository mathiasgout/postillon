"""Reads the entries, their posts and the history of the posts for the API (see docs/api.md).

The conditions of a list come from the API's filter; this module knows only the columns.
"""

from __future__ import annotations

import dataclasses
import operator
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, and_, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from postillon.db.models import Entry, Event, Post
from postillon.domain import Status
from postillon.platforms import PLATFORMS

COMPARISONS: dict[str, Callable[[Any, Any], Any]] = {
    "=": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
}


@dataclasses.dataclass(frozen=True)
class EntryQuery:
    """The entries of a list page: conditions on the entry, and on one of its posts."""

    # None for every project.
    project: str | None = None
    publish_at: tuple[tuple[str, datetime], ...] = ()
    status: Status | None = None
    platform: str | None = None
    manual: bool | None = None
    descending: bool = True
    # The (publish_at, id) of the last entry of the previous page.
    after: tuple[datetime, int] | None = None
    limit: int = 100


def get(session: Session, project: str, key: str) -> Entry | None:
    return session.scalar(
        select(Entry).where(Entry.project == project, Entry.key == key).options(selectinload(Entry.posts)),
    )


def get_post(session: Session, project: str, key: str, platform: str) -> Post | None:
    return session.scalar(
        select(Post)
        .join(Post.entry)
        .where(Entry.project == project, Entry.key == key, Post.platform == platform)
        .options(joinedload(Post.entry)),
    )


def find(session: Session, query: EntryQuery) -> Sequence[Entry]:
    """The entries the query selects, ordered by publication time then creation, at most `limit`."""
    statement = select(Entry).options(selectinload(Entry.posts))
    if query.project is not None:
        statement = statement.where(Entry.project == query.project)
    for comparison, value in query.publish_at:
        statement = statement.where(COMPARISONS[comparison](Entry.publish_at, value))
    post = _post_conditions(query)
    if post:
        statement = statement.where(Entry.posts.any(and_(*post)))
    if query.after is not None:
        statement = statement.where(_after(*query.after, query.descending))
    order = (Entry.publish_at.desc(), Entry.id.desc()) if query.descending else (Entry.publish_at, Entry.id)
    return session.scalars(statement.order_by(*order).limit(query.limit)).all()


def events(
    session: Session, project: str, key: str, *, platform: str | None, after: int | None, limit: int
) -> Sequence[Event]:
    """The events of one post of the entry, or of all its posts, in the order they were recorded."""
    statement = (
        select(Event)
        .join(Event.post)
        .join(Post.entry)
        .where(Entry.project == project, Entry.key == key)
        .options(joinedload(Event.post).joinedload(Post.entry))
    )
    if platform is not None:
        statement = statement.where(Post.platform == platform)
    if after is not None:
        statement = statement.where(Event.id > after)
    return session.scalars(statement.order_by(Event.id).limit(limit)).all()


def _post_conditions(query: EntryQuery) -> list[ColumnElement[bool]]:
    conditions = []
    if query.status is not None:
        conditions.append(Post.status == query.status)
    if query.platform is not None:
        conditions.append(Post.platform == query.platform)
    if query.manual is not None:
        manual = sorted(name for name, spec in PLATFORMS.items() if spec.manual)
        conditions.append(Post.platform.in_(manual) if query.manual else Post.platform.not_in(manual))
    return conditions


def _after(publish_at: datetime, entry_id: int, descending: bool) -> ColumnElement[bool]:
    if descending:
        return or_(Entry.publish_at < publish_at, and_(Entry.publish_at == publish_at, Entry.id < entry_id))
    return or_(Entry.publish_at > publish_at, and_(Entry.publish_at == publish_at, Entry.id > entry_id))
