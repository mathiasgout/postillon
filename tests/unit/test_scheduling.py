import dataclasses
from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from postillon.db.models import Post
from postillon.domain import PostState, Status
from postillon.errors import (
    ChangedMeanwhile,
    PlatformNotManual,
    PostNotFound,
    PublishAtPassed,
    TransitionRefused,
    VideoNotHeld,
)
from postillon.manifest import Manifest
from postillon.platforms.base import Task
from postillon.platforms.tiktok.client import TikTokPlatform
from postillon.services.publishing import Publisher
from postillon.services.scheduling import mark_scheduled
from postillon.services.submission import submit
from postillon.services.transaction import commit
from postillon.settings import Settings
from postillon.storage.videos import VideoStore
from tests.support import BEFORE, PUBLISH_AT, FakeBucket, give_video, posts

KEY = "day-23"


@pytest.fixture(autouse=True)
def entry(session_factory: sessionmaker[Session], settings: Settings, videos: VideoStore) -> None:
    m = Manifest.model_validate(
        {
            "publish_at": PUBLISH_AT.isoformat(),
            "posts": {"youtube": {"account": "main", "title": "Day 23"}, "tiktok": {"account": "main"}},
        },
    )
    with session_factory() as session:
        submit(session, settings, project="my-project", key=KEY, manifest=m, now=BEFORE)
        commit(session)
    give_video(session_factory, videos, KEY)


def schedule(
    session_factory: sessionmaker[Session], platform: str = "tiktok", now: datetime = BEFORE, key: str = KEY
) -> None:
    with session_factory() as session:
        mark_scheduled(session, project="my-project", key=key, platform=platform, now=now)
        commit(session)


def stored(session_factory: sessionmaker[Session]) -> dict[str, Post]:
    return posts(session_factory, KEY)


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


def test_post_no_longer_pending_is_refused(session_factory):
    schedule(session_factory)
    with pytest.raises(TransitionRefused, match="is scheduled"):
        schedule(session_factory)


def test_post_of_an_entry_without_video_is_refused(session_factory, settings: Settings):
    m = Manifest.model_validate({"publish_at": PUBLISH_AT.isoformat(), "posts": {"tiktok": {"account": "main"}}})
    with session_factory() as session:
        submit(session, settings, project="my-project", key="day-24", manifest=m, now=BEFORE)
        commit(session)
    with pytest.raises(VideoNotHeld):
        schedule(session_factory, key="day-24")


def test_post_past_its_publication_time_is_refused(session_factory):
    with pytest.raises(PublishAtPassed, match="has passed"):
        schedule(session_factory, now=PUBLISH_AT)
    assert stored(session_factory)["tiktok"].status == Status.PENDING


def test_post_changed_meanwhile_is_a_conflict(session_factory, monkeypatch: pytest.MonkeyPatch):
    def stale(self: Session) -> None:
        raise StaleDataError("changed")

    monkeypatch.setattr(Session, "commit", stale)
    with pytest.raises(ChangedMeanwhile, match="changed meanwhile"):
        schedule(session_factory)


class SchedulingYouTube:
    def step(self, task: Task) -> PostState:
        return dataclasses.replace(task.state, status=Status.SCHEDULED)


def test_video_waits_for_the_operator_then_the_post_is_published(
    session_factory, settings: Settings, videos: VideoStore, bucket: FakeBucket
):
    platforms = {"my-project": {"youtube": SchedulingYouTube(), "tiktok": TikTokPlatform()}}
    publisher = Publisher(session_factory, settings, platforms, videos, bucket)  # type: ignore[arg-type]
    publisher.run_pass(BEFORE)
    assert any(videos.root.rglob("*.mp4"))
    schedule(session_factory)
    publisher.run_pass(BEFORE + timedelta(minutes=1))
    assert not any((videos.root / "my-project").glob("*.mp4"))
    publisher.run_pass(PUBLISH_AT)
    assert stored(session_factory)["tiktok"].status == Status.PUBLISHED
