import io
from typing import Any

import pytest
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from postillon.db.models import Post
from postillon.domain import Status
from postillon.manifest import Manifest
from postillon.services import entries
from postillon.services.submission import (
    SubmissionConflict,
    SubmissionRefused,
    Submitted,
    UnknownProject,
    submit,
)
from postillon.settings import Settings
from postillon.storage.videos import VideoStore
from tests.support import BEFORE, MP4, PUBLISH_AT

KEY = "season-1/day-23"


def manifest(publish_at: str = "2026-10-22T18:00:00Z", **posts: Any) -> Manifest:
    if not posts:
        posts = {"youtube": {"account": "main", "title": "Day 23"}, "instagram": {"account": "main"}}
    return Manifest.model_validate({"publish_at": publish_at, "posts": posts})


@pytest.fixture
def send(session_factory: sessionmaker[Session], settings: Settings, videos: VideoStore):
    def send(m: Manifest | None = None, video: bytes | None = MP4, project: str = "my-project") -> Submitted:
        with session_factory() as session:
            return submit(
                session,
                settings,
                videos,
                project=project,
                key=KEY,
                manifest=m or manifest(),
                video=io.BytesIO(video) if video is not None else None,
                now=BEFORE,
            )

    return send


def stored(session_factory: sessionmaker[Session]) -> dict[str, Post]:
    with session_factory() as session:
        entry = entries.get(session, "my-project", KEY)
        assert entry is not None
        return {post.platform: post for post in entry.posts}


def set_status(session_factory: sessionmaker[Session], platform: str, status: Status) -> None:
    with session_factory() as session:
        entry = entries.get(session, "my-project", KEY)
        assert entry is not None
        next(p for p in entry.posts if p.platform == platform).status = status
        session.commit()


def test_new_entry_creates_its_posts_and_keeps_its_video(send, session_factory, videos: VideoStore):
    submitted = send()
    assert submitted.created
    assert submitted.ignored == []
    posts = stored(session_factory)
    assert {name: post.status for name, post in posts.items()} == {"youtube": "pending", "instagram": "pending"}
    assert posts["youtube"].content["title"] == "Day 23"
    assert [e.status for e in posts["youtube"].events] == [Status.PENDING]
    assert videos.path("my-project", KEY).read_bytes() == MP4
    assert submitted.entry.publish_at == PUBLISH_AT


def test_unknown_project_is_refused(send):
    with pytest.raises(UnknownProject):
        send(project="other")


def test_unconfigured_account_is_refused(send):
    with pytest.raises(SubmissionRefused, match="account 'other' is not configured for youtube"):
        send(manifest(youtube={"account": "other", "title": "Day 23"}))


def test_new_entry_without_video_is_refused(send, session_factory):
    with pytest.raises(SubmissionRefused, match="video is missing"):
        send(video=None)
    with session_factory() as session:
        assert entries.get(session, "my-project", KEY) is None


def test_invalid_video_writes_nothing(send, session_factory, videos: VideoStore):
    with pytest.raises(SubmissionRefused, match="not an MP4"):
        send(video=b"not a video")
    with session_factory() as session:
        assert entries.get(session, "my-project", KEY) is None
    assert not videos.exists("my-project", KEY)


def test_new_submission_replaces_a_post_not_sent(send, session_factory):
    send()
    submitted = send(manifest(youtube={"account": "main", "title": "Day 23 bis"}), video=None)
    assert not submitted.created
    posts = stored(session_factory)
    assert posts["youtube"].content["title"] == "Day 23 bis"
    assert "instagram" not in posts


def test_new_submission_leaves_a_sent_post_and_lists_it(send, session_factory):
    send()
    set_status(session_factory, "youtube", Status.SCHEDULED)
    submitted = send(manifest(youtube={"account": "main", "title": "Day 23 bis"}), video=None)
    assert submitted.ignored == ["youtube"]
    assert stored(session_factory)["youtube"].content["title"] == "Day 23"


def test_new_time_is_ignored_by_a_sent_post(send, session_factory):
    send()
    set_status(session_factory, "youtube", Status.SCHEDULED)
    submitted = send(manifest(publish_at="2026-10-23T18:00:00Z"), video=None)
    assert submitted.ignored == ["youtube"]


def test_rejected_post_is_tried_again(send, session_factory):
    send()
    set_status(session_factory, "instagram", Status.REJECTED)
    send(video=None)
    post = stored(session_factory)["instagram"]
    assert post.status == Status.PENDING
    assert [e.status for e in post.events] == [Status.PENDING, Status.PENDING]


def test_platform_removed_from_a_sent_entry_is_listed(send, session_factory):
    send()
    set_status(session_factory, "instagram", Status.PUBLISHED)
    submitted = send(manifest(youtube={"account": "main", "title": "Day 23"}), video=None)
    assert submitted.ignored == ["instagram"]
    assert set(stored(session_factory)) == {"youtube", "instagram"}


def test_video_is_required_again_once_released(send, videos: VideoStore, session_factory):
    send()
    videos.delete("my-project", KEY)
    with pytest.raises(SubmissionRefused, match="video is missing"):
        send(video=None)
    for platform in ("youtube", "instagram"):
        set_status(session_factory, platform, Status.PUBLISHED)
    send(video=None)


def test_conflicting_write_discards_the_new_video(send, videos: VideoStore, monkeypatch: pytest.MonkeyPatch):
    send()

    def stale(self: Session) -> None:
        raise StaleDataError("changed")

    monkeypatch.setattr(Session, "commit", stale)
    with pytest.raises(SubmissionConflict):
        send(video=MP4 + b"new")
    assert videos.path("my-project", KEY).read_bytes() == MP4
    assert list((videos.root / ".staging").iterdir()) == []
