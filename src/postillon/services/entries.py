"""Reads the entries and their history for the API (see docs/api.md)."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from postillon.db.models import Entry, Post
from postillon.domain import Status

_WITH_HISTORY = selectinload(Entry.posts).selectinload(Post.events)


def get(session: Session, project: str, key: str) -> Entry | None:
    return session.scalar(
        select(Entry).where(Entry.project == project, Entry.key == key).options(_WITH_HISTORY),
    )


def find(
    session: Session,
    project: str | None,
    status: Status | None,
    limit: int,
    offset: int,
) -> Sequence[Entry]:
    """The entries, latest publication first, of one project or all, with a post of one status or any."""
    query = select(Entry).options(_WITH_HISTORY).order_by(Entry.publish_at.desc(), Entry.id.desc())
    if project is not None:
        query = query.where(Entry.project == project)
    if status is not None:
        query = query.where(Entry.posts.any(Post.status == status))
    return session.scalars(query.limit(limit).offset(offset)).all()
