from typing import Any

import pytest
from sqlalchemy.orm import Session, sessionmaker

from postillon.db.models import Post
from postillon.domain import Status
from postillon.errors import AccountNotConfigured, ProjectNotFound
from postillon.manifest import Manifest
from postillon.services import entries
from postillon.services.submission import Submitted, submit
from postillon.services.transaction import commit
from postillon.settings import Settings
from tests.support import BEFORE, PUBLISH_AT, posts

KEY = "day-23"
LATER = PUBLISH_AT.replace(day=23)


def manifest(publish_at: str = "2026-10-22T18:00:00Z", **posts: Any) -> Manifest:
    if not posts:
        posts = {"youtube": {"account": "main", "title": "Day 23"}, "instagram": {"account": "main"}}
    return Manifest.model_validate({"publish_at": publish_at, "posts": posts})


@pytest.fixture
def send(session_factory: sessionmaker[Session], settings: Settings):
    def send(m: Manifest | None = None, project: str = "my-project") -> Submitted:
        with session_factory() as session:
            submitted = submit(session, settings, project=project, key=KEY, manifest=m or manifest(), now=BEFORE)
            commit(session)
            return submitted

    return send


def stored(session_factory: sessionmaker[Session]) -> dict[str, Post]:
    return posts(session_factory, KEY)


def set_status(session_factory: sessionmaker[Session], platform: str, status: Status) -> None:
    with session_factory() as session:
        entry = entries.get(session, "my-project", KEY)
        assert entry is not None
        next(p for p in entry.posts if p.platform == platform).status = status
        session.commit()


def test_new_entry_creates_its_posts_without_video(send, session_factory):
    submitted = send()
    assert submitted.created
    posts = stored(session_factory)
    assert {name: post.status for name, post in posts.items()} == {"youtube": "pending", "instagram": "pending"}
    assert posts["youtube"].content["title"] == "Day 23"
    assert posts["youtube"].publish_at == PUBLISH_AT
    assert [e.status for e in posts["youtube"].events] == [Status.PENDING]
    assert submitted.entry.publish_at == PUBLISH_AT
    assert submitted.entry.video_sha256 is None


def test_unknown_project_is_refused(send):
    with pytest.raises(ProjectNotFound):
        send(project="other")


def test_unconfigured_account_is_refused(send, session_factory):
    with pytest.raises(AccountNotConfigured, match="account 'other' is not configured for youtube"):
        send(manifest(youtube={"account": "other", "title": "Day 23"}))
    with session_factory() as session:
        assert entries.get(session, "my-project", KEY) is None


def test_new_submission_replaces_a_post_not_sent(send, session_factory):
    send()
    submitted = send(manifest("2026-10-23T18:00:00Z", youtube={"account": "main", "title": "Day 23 bis"}))
    assert not submitted.created
    posts = stored(session_factory)
    assert (posts["youtube"].content["title"], posts["youtube"].publish_at) == ("Day 23 bis", LATER)
    assert "instagram" not in posts


def test_new_submission_leaves_a_sent_post_as_it_was_sent(send, session_factory):
    send()
    set_status(session_factory, "youtube", Status.SCHEDULED)
    send(manifest("2026-10-23T18:00:00Z", youtube={"account": "main", "title": "Day 23 bis"}))
    post = stored(session_factory)["youtube"]
    assert (post.content["title"], post.publish_at) == ("Day 23", PUBLISH_AT)


def test_rejected_post_is_tried_again(send, session_factory):
    send()
    set_status(session_factory, "instagram", Status.REJECTED)
    send()
    post = stored(session_factory)["instagram"]
    assert post.status == Status.PENDING
    assert [e.status for e in post.events] == [Status.PENDING, Status.PENDING]


def test_platform_removed_from_a_sent_entry_keeps_its_post(send, session_factory):
    send()
    set_status(session_factory, "instagram", Status.PUBLISHED)
    send(manifest(youtube={"account": "main", "title": "Day 23"}))
    assert set(stored(session_factory)) == {"youtube", "instagram"}


def test_every_write_bumps_the_entry_version(send, session_factory):
    first = send().entry.version
    assert send(manifest("2026-10-23T18:00:00Z")).entry.version == first + 1
