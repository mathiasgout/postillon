"""Records an entry a producer submits: its manifest, its posts and its video (see docs/api.md).

Called by the API; a submission is checked whole before anything is written, and never
changes a post that may have reached its platform.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import Any, BinaryIO

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.exc import StaleDataError

from postillon.db.models import Entry, Event, Post
from postillon.domain import HOLDS_VIDEO, SENT, Status
from postillon.manifest import Manifest
from postillon.platforms.base import PlatformPost
from postillon.settings import Settings
from postillon.storage.videos import InvalidVideo, VideoStore


class UnknownProject(LookupError):
    pass


class SubmissionRefused(ValueError):
    pass


class SubmissionConflict(Exception):
    """The worker changed a post of the entry meanwhile; submitting again settles it."""


@dataclasses.dataclass(frozen=True)
class Submitted:
    entry: Entry
    created: bool
    # Platforms whose post may have reached the platform, left as they were sent.
    ignored: list[str]


def submit(
    session: Session,
    settings: Settings,
    videos: VideoStore,
    *,
    project: str,
    key: str,
    manifest: Manifest,
    video: BinaryIO | None,
    now: datetime,
) -> Submitted:
    """Creates or replaces the entry; raises UnknownProject, SubmissionRefused or
    SubmissionConflict, having written nothing."""
    posts = check_accounts(settings, project, manifest)
    entry = session.scalar(
        select(Entry).where(Entry.project == project, Entry.key == key).options(selectinload(Entry.posts)),
    )
    current = {post.platform: post for post in entry.posts} if entry else {}
    if video is None and not videos.exists(project, key) and any(_needs_video(current.get(name)) for name in posts):
        raise SubmissionRefused("video is missing")
    try:
        staged = videos.stage(video) if video is not None else None
    except InvalidVideo as e:
        raise SubmissionRefused(str(e)) from None
    created = entry is None
    try:
        if entry is None:
            entry = Entry(project=project, key=key, submitted_at=now, posts=[])
            session.add(entry)
        rescheduled = not created and entry.publish_at != manifest.publish_at
        entry.publish_at = manifest.publish_at
        entry.manifest = manifest.model_dump(mode="json", exclude_none=True)
        entry.updated_at = now
        if staged is not None:
            entry.video_released_at = None
        ignored = _apply_posts(entry, posts, current, rescheduled, now)
        session.commit()
    except BaseException as e:
        session.rollback()
        if staged is not None:
            videos.discard(staged)
        if isinstance(e, StaleDataError):
            raise SubmissionConflict("a post of the entry changed meanwhile, submit again") from None
        raise
    if staged is not None:
        videos.promote(staged, project, key)
    return Submitted(entry=entry, created=created, ignored=ignored)


def check_accounts(settings: Settings, project: str, manifest: Manifest) -> dict[str, PlatformPost]:
    """The manifest's posts, each with an account configured in the project."""
    configured = settings.projects.get(project)
    if configured is None:
        raise UnknownProject(f"project {project!r} is not configured")
    posts = manifest.posts.by_platform()
    for name, post in posts.items():
        if post.account not in configured.accounts(name):
            raise SubmissionRefused(f"account {post.account!r} is not configured for {name} in {project}")
    return posts


def _needs_video(post: Post | None) -> bool:
    return post is None or post.status not in HOLDS_VIDEO


def _apply_posts(
    entry: Entry,
    posts: dict[str, PlatformPost],
    current: dict[str, Post],
    rescheduled: bool,
    now: datetime,
) -> list[str]:
    """Adds, replaces or removes the entry's posts after the manifest; returns the platforms whose
    post was sent already and stays as it was."""
    ignored = []
    for name, post in posts.items():
        content = post.model_dump(mode="json")
        existing = current.pop(name, None)
        if existing is None:
            entry.posts.append(
                Post(
                    platform=name,
                    account=post.account,
                    content=content,
                    status=Status.PENDING,
                    failures=0,
                    extra={},
                    updated_at=now,
                    events=[Event(status=Status.PENDING, at=now)],
                )
            )
        elif existing.status in SENT:
            if rescheduled or existing.content != content:
                ignored.append(name)
        elif existing.content != content or existing.status == Status.REJECTED:
            _replace(existing, post.account, content, now)
    for name, existing in current.items():
        if existing.status in SENT:
            ignored.append(name)
        else:
            entry.posts.remove(existing)
    return sorted(ignored)


def _replace(post: Post, account: str, content: dict[str, Any], now: datetime) -> None:
    """Gives a post not sent yet its new content; a rejected post is tried again."""
    post.account = account
    post.content = content
    post.failures = 0
    post.updated_at = now
    if post.status == Status.REJECTED:
        post.status = Status.PENDING
        post.error = None
        post.events.append(Event(status=Status.PENDING, at=now))
