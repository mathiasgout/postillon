"""Records an entry published outside the service, its posts already `published` (see docs/api.md).

Called by the API; the worker never steps a published post, and the service holds no video of it.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from postillon.db.models import Entry, Post
from postillon.domain import Actor, Status
from postillon.errors import EntryExists, PublicationInFuture, PublicationsMismatch
from postillon.manifest import Manifest
from postillon.services.submission import check_accounts
from postillon.settings import Settings


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
    """Creates the entry with its posts `published`; raises ProjectNotFound, AccountNotConfigured,
    PublicationsMismatch, PublicationInFuture or EntryExists, having written nothing. A record never
    changes an existing entry."""
    posts = check_accounts(settings, project, manifest)
    if set(published) != set(posts):
        raise PublicationsMismatch(f"published must name the platforms of the posts: {', '.join(sorted(posts))}")
    future = sorted(name for name, publication in published.items() if publication.at > now)
    if future:
        raise PublicationInFuture(f"a publication time is in the future: {', '.join(future)}")
    if session.scalar(select(Entry.id).where(Entry.project == project, Entry.key == key)) is not None:
        raise EntryExists(f"entry {project}/{key} exists already")
    entry = Entry(
        project=project,
        key=key,
        publish_at=manifest.publish_at,
        manifest=manifest.model_dump(mode="json", exclude_none=True),
        submitted_at=now,
        updated_at=now,
        video_released_at=now,
        posts=[
            Post.new(
                platform=name,
                account=post.account,
                content=post.model_dump(mode="json"),
                status=Status.PUBLISHED,
                actor=Actor.PRODUCER,
                now=now,
                since=published[name].at,
                remote_id=published[name].remote_id,
            )
            for name, post in posts.items()
        ],
    )
    session.add(entry)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise EntryExists(f"entry {project}/{key} exists already") from None
    return entry
