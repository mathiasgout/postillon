import dataclasses
import io
from collections.abc import Callable
from datetime import datetime, timedelta

import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session, sessionmaker

from postillon.db.models import Post
from postillon.domain import PostState, Status
from postillon.manifest import Manifest
from postillon.platforms.base import Task
from postillon.services import entries
from postillon.services.publishing import Publisher
from postillon.services.submission import submit
from postillon.settings import Settings
from postillon.storage.videos import VideoStore
from tests.support import BEFORE, MP4, PUBLISH_AT, FakeBucket


class FakePlatform:
    """Schedules every post it is handed, unless a test gives it another behaviour."""

    def __init__(self) -> None:
        self.tasks: list[Task] = []
        self.behaviour: Callable[[Task], PostState] = lambda task: dataclasses.replace(
            task.state, status=Status.SCHEDULED, remote_id="v1"
        )

    def step(self, task: Task) -> PostState:
        self.tasks.append(task)
        return self.behaviour(task)


@pytest.fixture
def platform() -> FakePlatform:
    return FakePlatform()


@pytest.fixture
def publisher(session_factory, settings: Settings, videos: VideoStore, bucket: FakeBucket, platform: FakePlatform):
    return Publisher(session_factory, settings, {"my-project": {"youtube": platform}}, videos, bucket)  # type: ignore[arg-type]


@pytest.fixture
def send(session_factory: sessionmaker[Session], settings: Settings, videos: VideoStore):
    def send(key: str = "day-23", publish_at: datetime = PUBLISH_AT, account: str = "main") -> None:
        m = Manifest.model_validate(
            {"publish_at": publish_at.isoformat(), "posts": {"youtube": {"account": account, "title": key}}}
        )
        with session_factory() as session:
            submit(
                session, settings, videos, project="my-project", key=key, manifest=m, video=io.BytesIO(MP4), now=BEFORE
            )

    return send


def post(session_factory: sessionmaker[Session], key: str = "day-23") -> Post:
    with session_factory() as session:
        entry = entries.get(session, "my-project", key)
        assert entry is not None
        return entry.posts[0]


def test_pending_post_is_stepped_and_its_change_recorded(publisher, platform, send, session_factory):
    send()
    publisher.run_pass(BEFORE)
    task = platform.tasks[0]
    assert (task.post.account, task.publish_at, task.state.status) == ("main", PUBLISH_AT, Status.PENDING)
    stepped = post(session_factory)
    assert (stepped.status, stepped.remote_id, stepped.updated_at) == (Status.SCHEDULED, "v1", BEFORE)
    assert [(e.status, e.at) for e in stepped.events] == [(Status.PENDING, BEFORE), (Status.SCHEDULED, BEFORE)]


def test_scheduled_post_waits_for_its_publication_time(publisher, platform, send):
    send()
    publisher.run_pass(BEFORE)
    publisher.run_pass(BEFORE + timedelta(hours=1))
    assert len(platform.tasks) == 1
    publisher.run_pass(PUBLISH_AT)
    assert len(platform.tasks) == 2


def test_published_post_is_never_stepped_again(publisher, platform, send):
    send()
    platform.behaviour = lambda task: dataclasses.replace(task.state, status=Status.PUBLISHED)
    publisher.run_pass(PUBLISH_AT)
    publisher.run_pass(PUBLISH_AT + timedelta(days=1))
    assert len(platform.tasks) == 1


def test_exception_fails_the_post_and_spaces_the_retries(publisher, platform, send, session_factory):
    send()

    def boom(task: Task) -> PostState:
        raise RuntimeError("quota")

    platform.behaviour = boom
    publisher.run_pass(BEFORE)
    failed = post(session_factory)
    assert (failed.status, failed.error, failed.failures) == (Status.FAILED, "RuntimeError: quota", 1)
    publisher.run_pass(BEFORE + timedelta(seconds=59))
    assert len(platform.tasks) == 1
    publisher.run_pass(BEFORE + timedelta(minutes=1))
    assert len(platform.tasks) == 2
    assert post(session_factory).failures == 2
    publisher.run_pass(BEFORE + timedelta(minutes=2, seconds=59))
    assert len(platform.tasks) == 2


def test_checkpoint_is_kept_when_the_step_fails(publisher, platform, send, session_factory):
    send()

    def interrupted(task: Task) -> PostState:
        task.checkpoint(dataclasses.replace(task.state, status=Status.IN_PROGRESS, extra={"uploading": True}))
        raise ConnectionError("reset")

    platform.behaviour = interrupted
    publisher.run_pass(BEFORE)
    failed = post(session_factory)
    assert (failed.status, failed.extra) == (Status.FAILED, {"uploading": True})
    assert [e.status for e in failed.events] == [Status.PENDING, Status.IN_PROGRESS, Status.FAILED]


def test_post_of_an_unconfigured_account_is_rejected(publisher, platform, send, session_factory, settings: Settings):
    send()
    publisher.settings = settings.model_copy(
        update={"projects": {"my-project": settings.projects["my-project"].model_copy(update={"youtube": {}})}}
    )
    publisher.run_pass(BEFORE)
    assert platform.tasks == []
    rejected = post(session_factory)
    assert rejected.status == Status.REJECTED
    assert "not configured" in str(rejected.error)


def test_video_is_released_once_every_platform_holds_it(publisher, send, session_factory, videos, bucket):
    send()
    publisher.run_pass(BEFORE)
    assert not videos.exists("my-project", "day-23")
    assert bucket.deleted == [("my-project", "day-23")]
    with session_factory() as session:
        entry = entries.get(session, "my-project", "day-23")
        assert entry is not None
        assert entry.video_released_at == BEFORE
    publisher.run_pass(PUBLISH_AT)
    assert bucket.deleted == [("my-project", "day-23")]


def test_video_is_kept_while_a_platform_waits(publisher, platform, send, videos, bucket):
    send()
    platform.behaviour = lambda task: task.state
    publisher.run_pass(BEFORE)
    assert videos.exists("my-project", "day-23")
    assert bucket.deleted == []


def test_next_publication_of_the_account_is_handed_over(publisher, platform, send):
    send("day-23")
    send("day-24", PUBLISH_AT + timedelta(days=1))
    send("day-23-bis", PUBLISH_AT + timedelta(hours=1))
    platform.behaviour = lambda task: task.state
    publisher.run_pass(BEFORE)
    by_key = {task.post.title: task.next_publish_at for task in platform.tasks}  # type: ignore[attr-defined]
    assert by_key["day-23"] == PUBLISH_AT + timedelta(hours=1)
    assert by_key["day-24"] is None


def test_post_changed_by_the_api_meanwhile_is_left_for_the_next_pass(publisher, platform, send, session_factory):
    send()

    def concurrent(task: Task) -> PostState:
        with session_factory() as other:
            other.execute(update(Post).values(version=Post.version + 1, content={"account": "main", "title": "new"}))
            other.commit()
        return dataclasses.replace(task.state, status=Status.SCHEDULED, remote_id="v1")

    platform.behaviour = concurrent
    publisher.run_pass(BEFORE)
    kept = post(session_factory)
    assert (kept.status, kept.content["title"]) == (Status.PENDING, "new")
