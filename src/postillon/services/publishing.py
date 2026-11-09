"""One pass of the worker: hands every post that has something due to its platform, records the
outcome, and deletes the video copies once every platform holds the video (see docs/statuses.md).

Each post is stepped in its own transaction; a post the API changed meanwhile is left for the
next pass.
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Mapping
from datetime import datetime, timedelta

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session, joinedload, sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from postillon.db.models import Entry, Post
from postillon.domain import ACTIVE, HOLDS_VIDEO, Actor, PostState, Status
from postillon.platforms import PLATFORMS
from postillon.platforms.base import Platform, Task
from postillon.settings import Settings
from postillon.storage.bucket import Bucket
from postillon.storage.videos import StoredVideo, VideoStore

log = logging.getLogger(__name__)

# Every new YouTube upload counts against a daily quota shared by the channels of a Google Cloud
# project: a lasting failure retried each minute would exhaust it within hours.
RETRY_FIRST = timedelta(minutes=1)
RETRY_MAX = timedelta(hours=1)


class Publisher:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        settings: Settings,
        platforms: Mapping[str, Mapping[str, Platform]],
        videos: VideoStore,
        bucket: Bucket,
    ):
        """`platforms` holds the client of each configured platform, by project then platform."""
        self.sessions = sessions
        self.settings = settings
        self.platforms = platforms
        self.videos = videos
        self.bucket = bucket

    def run_pass(self, now: datetime) -> None:
        with self.sessions() as session:
            posts = session.scalars(
                select(Post).where(Post.status.in_(sorted(ACTIVE))).options(joinedload(Post.entry)),
            ).all()
            due = [post.id for post in posts if _is_due(post, now)]
        for post_id in due:
            try:
                self._step(post_id, now)
            except Exception:
                log.exception("post %s: step not recorded", post_id)
        try:
            self._release_videos(now)
        except Exception:
            log.exception("video release failed")

    def _step(self, post_id: int, now: datetime) -> None:
        with self.sessions() as session:
            post = session.get(Post, post_id, options=[joinedload(Post.entry)])
            if post is None or post.status not in ACTIVE:
                return
            entry = post.entry
            platform = self.platforms.get(entry.project, {}).get(post.platform)
            project = self.settings.projects.get(entry.project)
            current = _state(post)
            if platform is None or project is None or post.account not in project.accounts(post.platform):
                # The configuration changed since the submission.
                new = dataclasses.replace(
                    current,
                    status=Status.REJECTED,
                    error=f"account {post.account!r} is not configured for {post.platform} in {entry.project}",
                )
            else:
                new = self._run(session, platform, post, current, now)
            _record(post, new, now)
            try:
                session.commit()
            except StaleDataError:
                log.warning(
                    "%s/%s %s: changed meanwhile, left for the next pass", entry.project, entry.key, post.platform
                )

    def _run(self, session: Session, platform: Platform, post: Post, current: PostState, now: datetime) -> PostState:
        entry = post.entry

        def checkpoint(state: PostState) -> None:
            _record(post, state, now)
            session.commit()

        task = Task(
            post=PLATFORMS[post.platform].post.model_validate(post.content),
            publish_at=entry.publish_at,
            state=current,
            now=now,
            video=StoredVideo(self.videos, self.bucket, entry.project, entry.key),
            checkpoint=checkpoint,
            next_publish_at=_next_publish_at(session, post),
        )
        try:
            return platform.step(task)
        except StaleDataError:
            raise
        except Exception as e:
            log.exception("%s/%s %s: step failed", entry.project, entry.key, post.platform)
            # From the last checkpoint, whose fields tell the platform what may have reached it.
            return dataclasses.replace(_state(post), status=Status.FAILED, error=f"{type(e).__name__}: {e}")

    def _release_videos(self, now: datetime) -> None:
        """Deletes both copies of each video every platform holds; the bucket copy first, so that a
        crash in between leaves a local file rather than a forgotten object."""
        held = ~exists().where(Post.entry_id == Entry.id, Post.status.not_in(HOLDS_VIDEO))
        with self.sessions() as session:
            for entry in session.scalars(select(Entry).where(Entry.video_released_at.is_(None), held)):
                self.bucket.delete_video(entry.project, entry.key)
                self.videos.delete(entry.project, entry.key)
                entry.video_released_at = now
                session.commit()


def _state(post: Post) -> PostState:
    return PostState(status=post.status, remote_id=post.remote_id, error=post.error, extra=dict(post.extra))


def _record(post: Post, new: PostState, now: datetime) -> None:
    """Writes the platform's state on the post, dated and logged when it changes; the attempts that
    follow a failure leave no event until one of them succeeds."""
    # The checkpoint of an attempt keeps the count, without which the retry delay never grows.
    retrying = post.failures > 0 and new.status in (Status.IN_PROGRESS, Status.FAILED)
    failures = post.failures + 1 if new.status == Status.FAILED else post.failures if retrying else 0
    error = new.error if new.status in (Status.FAILED, Status.REJECTED) else None
    values = (new.status, new.remote_id, error, new.extra, failures)
    if values == (post.status, post.remote_id, post.error, post.extra, post.failures):
        return
    if new.status != post.status:
        if not retrying:
            entry = post.entry
            log.info(
                "%s/%s %s: %s -> %s%s",
                entry.project,
                entry.key,
                post.platform,
                post.status,
                new.status,
                f" ({error})" if error else "",
            )
        post.move(new.status, Actor.WORKER, now, error, dated=not retrying)
    post.remote_id, post.error, post.extra, post.failures = new.remote_id, error, new.extra, failures
    post.updated_at = now


def _is_due(post: Post, now: datetime) -> bool:
    """Whether the platform has something to do: a `failed` post waits for its retry delay, and a
    `scheduled` one for its publication time, to confirm it."""
    if post.status == Status.FAILED:
        return now >= post.updated_at + _retry_delay(post.failures)
    if post.status == Status.SCHEDULED:
        return now >= post.entry.publish_at
    return True


def _retry_delay(failures: int) -> timedelta:
    """1, 2, 4... minutes after the last of `failures` consecutive failures, one hour at most."""
    return min(RETRY_FIRST * (1 << (min(max(failures, 1), 7) - 1)), RETRY_MAX)


def _next_publish_at(session: Session, post: Post) -> datetime | None:
    entry = post.entry
    return session.scalar(
        select(func.min(Entry.publish_at))
        .join(Entry.posts)
        .where(
            Entry.project == entry.project,
            Post.platform == post.platform,
            Post.account == post.account,
            Entry.publish_at > entry.publish_at,
        ),
    )
