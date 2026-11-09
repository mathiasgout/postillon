"""Records the operator's word that a manual platform holds the video of a post (see docs/api.md).

Called by the API, which commits; the worker then confirms the publication at `publish_at`.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from postillon.db.models import Entry, Post
from postillon.domain import Actor, Status
from postillon.errors import PlatformNotManual, PostNotFound, PublishAtPassed
from postillon.platforms import PLATFORMS

log = logging.getLogger(__name__)


def mark_scheduled(session: Session, *, project: str, key: str, platform: str, now: datetime) -> Post:
    """Moves a pending post of a manual platform to `scheduled`; raises PostNotFound,
    PlatformNotManual, PublishAtPassed or TransitionRefused, having changed nothing."""
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
    if now >= post.publish_at:
        raise PublishAtPassed(f"publish_at {post.publish_at.isoformat()} has passed")
    post.move(Status.SCHEDULED, Actor.OPERATOR, now)
    log.info("%s/%s %s: pending -> scheduled (operator)", project, key, platform)
    return post
