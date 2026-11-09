"""Records the operator's word that a manual platform holds the video of a post (see docs/api.md).

Called by the API; the worker then confirms the publication at `publish_at`.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.exc import StaleDataError

from postillon.db.models import Entry, Event, Post
from postillon.domain import Status
from postillon.platforms import PLATFORMS

log = logging.getLogger(__name__)


class PostNotFound(LookupError):
    pass


class NotManual(ValueError):
    pass


class SchedulingConflict(Exception):
    """The post is no longer pending, its publication time has passed, or the worker changed it meanwhile."""


def mark_scheduled(session: Session, *, project: str, key: str, platform: str, now: datetime) -> None:
    """Moves a pending post of a manual platform to `scheduled`; raises PostNotFound, NotManual or
    SchedulingConflict, having written nothing."""
    post = session.scalar(
        select(Post)
        .join(Post.entry)
        .where(Entry.project == project, Entry.key == key, Post.platform == platform)
        .options(joinedload(Post.entry)),
    )
    if post is None:
        raise PostNotFound(f"entry {project}/{key} has no {platform} post")
    if not PLATFORMS[platform].manual:
        raise NotManual(f"{platform} is published by the service, not by the operator")
    if post.status != Status.PENDING:
        raise SchedulingConflict(f"the {platform} post is {post.status}, not pending")
    if now >= post.entry.publish_at:
        raise SchedulingConflict(f"publish_at {post.entry.publish_at.isoformat()} has passed")
    post.status = Status.SCHEDULED
    post.updated_at = now
    post.events.append(Event(status=Status.SCHEDULED, at=now))
    try:
        session.commit()
    except StaleDataError:
        session.rollback()
        raise SchedulingConflict(f"the {platform} post changed meanwhile, check it again") from None
    log.info("%s/%s %s: pending -> scheduled (operator)", project, key, platform)
