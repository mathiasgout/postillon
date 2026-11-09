"""Records the operator's word that a manual platform holds the video of a post (see docs/api.md).

Called by the API; the worker then confirms the publication at `publish_at`.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.exc import StaleDataError

from postillon.db.models import Entry, Post
from postillon.domain import Actor, Status
from postillon.errors import PlatformNotManual, PostChanged, PostNotFound, PublishAtPassed
from postillon.platforms import PLATFORMS

log = logging.getLogger(__name__)


def mark_scheduled(session: Session, *, project: str, key: str, platform: str, now: datetime) -> None:
    """Moves a pending post of a manual platform to `scheduled`; raises PostNotFound,
    PlatformNotManual, TransitionRefused, PublishAtPassed or PostChanged, having written nothing."""
    post = session.scalar(
        select(Post)
        .join(Post.entry)
        .where(Entry.project == project, Entry.key == key, Post.platform == platform)
        .options(joinedload(Post.entry)),
    )
    if post is None:
        raise PostNotFound(f"entry {project}/{key} has no {platform} post")
    if not PLATFORMS[platform].manual:
        raise PlatformNotManual(f"{platform} is published by the service, not by the operator")
    if now >= post.entry.publish_at:
        raise PublishAtPassed(f"publish_at {post.entry.publish_at.isoformat()} has passed")
    post.move(Status.SCHEDULED, Actor.OPERATOR, now)
    try:
        session.commit()
    except StaleDataError:
        session.rollback()
        raise PostChanged(f"the {platform} post changed meanwhile, check it again") from None
    log.info("%s/%s %s: pending -> scheduled (operator)", project, key, platform)
