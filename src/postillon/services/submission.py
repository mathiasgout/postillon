"""Records the manifest a producer submits for an entry: its publication time and its posts (see
docs/api.md).

Called by the API, which commits; never changes a post that may have reached its platform.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from postillon.db.models import Entry, Post
from postillon.domain import SENT, Actor, Status
from postillon.errors import AccountNotConfigured, ProjectNotFound
from postillon.manifest import Manifest
from postillon.platforms.base import PlatformPost
from postillon.settings import Settings


@dataclasses.dataclass(frozen=True)
class Submitted:
    entry: Entry
    created: bool


def submit(
    session: Session,
    settings: Settings,
    *,
    project: str,
    key: str,
    manifest: Manifest,
    now: datetime,
) -> Submitted:
    """Creates or replaces the entry; raises ProjectNotFound or AccountNotConfigured, having changed
    nothing."""
    posts = check_accounts(settings, project, manifest)
    entry = session.scalar(
        select(Entry).where(Entry.project == project, Entry.key == key).options(selectinload(Entry.posts)),
    )
    created = entry is None
    if entry is None:
        entry = Entry(project=project, key=key, submitted_at=now, posts=[])
        session.add(entry)
    entry.publish_at = manifest.publish_at
    entry.manifest = manifest.model_dump(mode="json", exclude_none=True)
    entry.updated_at = now
    _apply_posts(entry, posts, manifest.publish_at, now)
    return Submitted(entry=entry, created=created)


def check_accounts(settings: Settings, project: str, manifest: Manifest) -> dict[str, PlatformPost]:
    """The manifest's posts, each with an account configured in the project; raises ProjectNotFound
    or AccountNotConfigured."""
    configured = settings.projects.get(project)
    if configured is None:
        raise ProjectNotFound(f"project {project!r} is not configured")
    posts = manifest.posts.by_platform()
    for name, post in posts.items():
        if post.account not in configured.accounts(name):
            raise AccountNotConfigured(f"account {post.account!r} is not configured for {name} in {project}")
    return posts


def _apply_posts(entry: Entry, posts: dict[str, PlatformPost], publish_at: datetime, now: datetime) -> None:
    """Adds, replaces or removes the posts not sent yet after the manifest; a post that may have
    reached its platform keeps what it was sent with."""
    current = {post.platform: post for post in entry.posts}
    for name, post in posts.items():
        content = post.model_dump(mode="json")
        existing = current.pop(name, None)
        if existing is None:
            entry.posts.append(
                Post.new(
                    platform=name,
                    account=post.account,
                    content=content,
                    publish_at=publish_at,
                    status=Status.PENDING,
                    actor=Actor.PRODUCER,
                    now=now,
                )
            )
        elif existing.status not in SENT:
            _replace(existing, post.account, content, publish_at, now)
    for existing in current.values():
        if existing.status not in SENT:
            entry.posts.remove(existing)


def _replace(post: Post, account: str, content: dict[str, Any], publish_at: datetime, now: datetime) -> None:
    """Gives a post not sent yet its new content and time; a rejected post is tried again."""
    if (post.content, post.publish_at) == (content, publish_at) and post.status != Status.REJECTED:
        return
    post.account = account
    post.content = content
    post.publish_at = publish_at
    post.failures = 0
    post.updated_at = now
    if post.status == Status.REJECTED:
        post.move(Status.PENDING, Actor.PRODUCER, now)
