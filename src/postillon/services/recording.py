"""Records an entry published outside the service, its posts already `published` (see docs/api.md).

Called by the API; the worker never steps a published post, and the service holds no video of it.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from postillon.db.models import Entry, Event, Post
from postillon.domain import Status
from postillon.manifest import Manifest
from postillon.services.submission import SubmissionRefused, check_accounts
from postillon.settings import Settings


class RecordRefused(ValueError):
    pass


class RecordConflict(Exception):
    """The entry exists already: a record never changes an entry."""


@dataclasses.dataclass(frozen=True)
class Publication:
    at: datetime
    remote_id: str | None = None


def record(
    session: Session,
    settings: Settings,
    *,
    project: str,
    key: str,
    manifest: Manifest,
    published: dict[str, Publication],
    now: datetime,
) -> Entry:
    """Creates the entry with its posts `published`; raises UnknownProject, RecordRefused or
    RecordConflict, having written nothing."""
    try:
        posts = check_accounts(settings, project, manifest)
    except SubmissionRefused as e:
        raise RecordRefused(str(e)) from None
    if set(published) != set(posts):
        raise RecordRefused(f"published must name the platforms of the posts: {', '.join(sorted(posts))}")
    future = sorted(name for name, publication in published.items() if publication.at > now)
    if future:
        raise RecordRefused(f"a publication time is in the future: {', '.join(future)}")
    if session.scalar(select(Entry.id).where(Entry.project == project, Entry.key == key)) is not None:
        raise RecordConflict(f"entry {project}/{key} exists already")
    entry = Entry(
        project=project,
        key=key,
        publish_at=manifest.publish_at,
        manifest=manifest.model_dump(mode="json", exclude_none=True),
        submitted_at=now,
        updated_at=now,
        video_released_at=now,
        posts=[
            Post(
                platform=name,
                account=post.account,
                content=post.model_dump(mode="json"),
                status=Status.PUBLISHED,
                remote_id=published[name].remote_id,
                failures=0,
                extra={},
                updated_at=now,
                events=[Event(status=Status.PUBLISHED, at=published[name].at)],
            )
            for name, post in posts.items()
        ],
    )
    session.add(entry)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise RecordConflict(f"entry {project}/{key} exists already") from None
    return entry
