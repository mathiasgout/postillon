"""Records the operator's word that a manual platform holds the video of a post (see docs/api.md).

Called by the API, which commits; the worker then confirms the publication at `publish_at`.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from postillon.db.models import Post
from postillon.domain import Actor, Status
from postillon.errors import PlatformNotManual, PostNotFound, PublishAtPassed, VideoNotHeld
from postillon.platforms import PLATFORMS
from postillon.services import entries

log = logging.getLogger(__name__)


def mark_scheduled(session: Session, *, project: str, key: str, platform: str, now: datetime) -> Post:
    """Moves a pending post of a manual platform to `scheduled`; raises PostNotFound,
    PlatformNotManual, VideoNotHeld, PublishAtPassed or TransitionRefused, having changed nothing."""
    post = entries.get_post(session, project, key, platform)
    if post is None:
        raise PostNotFound(f"entry {project}/{key} has no {platform} post")
    if not PLATFORMS[platform].manual:
        raise PlatformNotManual(f"{platform} is published by the service, not by the operator")
    if not post.entry.holds_video:
        raise VideoNotHeld(f"entry {project}/{key} has no video to schedule on {platform}")
    if now >= post.publish_at:
        raise PublishAtPassed(f"publish_at {post.publish_at.isoformat()} has passed")
    post.move(Status.SCHEDULED, Actor.OPERATOR, now)
    log.info("%s/%s %s: pending -> scheduled (operator)", project, key, platform)
    return post
