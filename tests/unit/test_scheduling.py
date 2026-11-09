import dataclasses
import io
from datetime import timedelta

import pytest
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from postillon.db.models import Post
from postillon.domain import PostState, Status
from postillon.errors import PlatformNotManual, PostChanged, PostNotFound, PublishAtPassed, TransitionRefused
from postillon.manifest import Manifest
from postillon.platforms.base import Task
from postillon.platforms.tiktok.client import TikTokPlatform
from postillon.services import entries
from postillon.services.publishing import Publisher
from postillon.services.scheduling import mark_scheduled
from postillon.services.submission import submit
from postillon.settings import Settings
from postillon.storage.videos import VideoStore
from tests.support import BEFORE, MP4, PUBLISH_AT, FakeBucket

KEY = "season-1/day-23"


@pytest.fixture(autouse=True)
def entry(session_factory: sessionmaker[Session], settings: Settings, videos: VideoStore) -> None:
    m = Manifest.model_validate(
        {
            "publish_at": PUBLISH_AT.isoformat(),
            "posts": {"youtube": {"account": "main", "title": "Day 23"}, "tiktok": {"account": "main"}},
        },
    )
    with session_factory() as session:
        submit(session, settings, videos, project="my-project", key=KEY, manifest=m, video=io.BytesIO(MP4), now=BEFORE)


def schedule(session_factory: sessionmaker[Session], platform: str = "tiktok", now=BEFORE, key: str = KEY) -> None:
    with session_factory() as session:
        mark_scheduled(session, project="my-project", key=key, platform=platform, now=now)


def stored(session_factory: sessionmaker[Session]) -> dict[str, Post]:
    with session_factory() as session:
        found = entries.get(session, "my-project", KEY)
        assert found is not None
        return {post.platform: post for post in found.posts}


def test_pending_post_is_scheduled_with_its_event(session_factory):
    schedule(session_factory, now=BEFORE + timedelta(hours=1))
    post = stored(session_factory)["tiktok"]
    assert (post.status, post.updated_at) == (Status.SCHEDULED, BEFORE + timedelta(hours=1))
    assert [e.status for e in post.events] == [Status.PENDING, Status.SCHEDULED]


@pytest.mark.parametrize(
    ("platform", "key", "error", "message"),
    [
        ("tiktok", "unknown", PostNotFound, "entry my-project/unknown has no tiktok post"),
        ("instagram", KEY, PostNotFound, "has no instagram post"),
        ("youtube", KEY, PlatformNotManual, "youtube is published by the service"),
    ],
)
def test_refused_post(session_factory, platform: str, key: str, error: type[Exception], message: str):
    with pytest.raises(error, match=message):
        schedule(session_factory, platform, key=key)


def test_post_no_longer_pending_is_a_conflict(session_factory):
    schedule(session_factory)
    with pytest.raises(TransitionRefused, match="is scheduled"):
        schedule(session_factory)


def test_post_past_its_publication_time_is_a_conflict(session_factory):
    with pytest.raises(PublishAtPassed, match="has passed"):
        schedule(session_factory, now=PUBLISH_AT)
    assert stored(session_factory)["tiktok"].status == Status.PENDING


def test_post_changed_meanwhile_is_a_conflict(session_factory, monkeypatch: pytest.MonkeyPatch):
    def stale(self: Session) -> None:
        raise StaleDataError("changed")

    monkeypatch.setattr(Session, "commit", stale)
    with pytest.raises(PostChanged, match="changed meanwhile"):
        schedule(session_factory)


class SchedulingYouTube:
    def step(self, task: Task) -> PostState:
        return dataclasses.replace(task.state, status=Status.SCHEDULED)


def test_video_waits_for_the_operator_then_the_post_is_published(
    session_factory, settings: Settings, videos: VideoStore, bucket: FakeBucket
):
    platforms = {"my-project": {"youtube": SchedulingYouTube(), "tiktok": TikTokPlatform()}}
    publisher = Publisher(session_factory, settings, platforms, videos, bucket)
    publisher.run_pass(BEFORE)
    assert videos.exists("my-project", KEY)
    schedule(session_factory)
    publisher.run_pass(BEFORE + timedelta(minutes=1))
    assert not videos.exists("my-project", KEY)
    publisher.run_pass(PUBLISH_AT)
    assert stored(session_factory)["tiktok"].status == Status.PUBLISHED
