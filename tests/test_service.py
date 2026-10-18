import dataclasses
import json
from datetime import UTC, datetime, timedelta

import pytest

from postillon import Bucket, Entry
from postillon.platforms.youtube import YouTube
from postillon.service import ProjectRunner
from postillon.state import Status
from tests.fake_s3 import FakeS3

PUBLISH_AT = datetime(2026, 10, 19, 6, 0, tzinfo=UTC)
BEFORE = PUBLISH_AT - timedelta(days=1)
ENTRY_ID = "pasta-in-ten-minutes"
STATE_KEY = f"my-project/states/{ENTRY_ID}.json"
VIDEO_KEY = f"my-project/videos/{ENTRY_ID}.mp4"


class FakeAdapter:
    """Schedules every post it is handed, unless a test gives it another behaviour."""

    def __init__(self):
        self.tasks = []
        self.behaviour = lambda task: dataclasses.replace(task.state, status=Status.SCHEDULED, remote_id="vid")

    def step(self, task):
        self.tasks.append(task)
        return self.behaviour(task)


@pytest.fixture
def s3():
    return FakeS3()


@pytest.fixture
def bucket(s3):
    return Bucket(s3, "videos", "my-project")


@pytest.fixture
def adapter():
    return FakeAdapter()


@pytest.fixture
def runner(bucket, adapter):
    return ProjectRunner(bucket, {"youtube": adapter}, {"youtube": {"my-youtube"}})


@pytest.fixture
def submit(bucket, tmp_path):
    video = tmp_path / "pasta.mp4"
    video.write_bytes(b"video")

    def submit(title="Pasta in ten minutes", account="my-youtube", publish_at=PUBLISH_AT):
        entry = Entry(id=ENTRY_ID, publish_at=publish_at, posts=[YouTube(account=account, title=title)])
        bucket.submit(entry, video)

    return submit


def run(runner, now, tmp_path):
    runner.run_pass(now, tmp_path / "work")


def state(s3):
    return json.loads(s3.objects[("videos", STATE_KEY)])


def test_new_entry_is_handed_to_its_adapter(runner, adapter, submit, s3, tmp_path):
    submit()
    run(runner, BEFORE, tmp_path)
    assert [t.post.title for t in adapter.tasks] == ["Pasta in ten minutes"]
    post = state(s3)["posts"]["youtube"]
    assert post["status"] == "scheduled"
    assert post["remote_id"] == "vid"
    assert post["manifest_sha256"] == state(s3)["manifest_sha256"]
    assert post["updated_at"] == "2026-10-18T06:00:00Z"


def test_video_is_deleted_once_every_platform_holds_it(runner, submit, s3, tmp_path):
    submit()
    run(runner, BEFORE, tmp_path)
    assert ("videos", VIDEO_KEY) not in s3.objects


def test_scheduled_post_waits_for_its_publication_time(runner, adapter, submit, s3, tmp_path):
    submit()
    run(runner, BEFORE, tmp_path)
    writes = len(s3.writes)
    run(runner, BEFORE + timedelta(hours=1), tmp_path)
    assert len(adapter.tasks) == 1
    assert len(s3.writes) == writes


def test_scheduled_post_is_confirmed_at_its_publication_time(runner, adapter, submit, s3, tmp_path):
    submit()
    run(runner, BEFORE, tmp_path)
    adapter.behaviour = lambda task: dataclasses.replace(task.state, status=Status.PUBLISHED)
    run(runner, PUBLISH_AT, tmp_path)
    assert len(adapter.tasks) == 2
    assert state(s3)["posts"]["youtube"]["status"] == "published"


def test_changed_manifest_reaches_a_post_not_sent_yet(runner, adapter, submit, s3, tmp_path):
    adapter.behaviour = lambda task: task.state
    submit()
    run(runner, BEFORE, tmp_path)
    submit(title="Pasta in nine minutes")
    run(runner, BEFORE, tmp_path)
    assert [t.post.title for t in adapter.tasks] == ["Pasta in ten minutes", "Pasta in nine minutes"]
    assert state(s3)["posts"]["youtube"]["manifest_sha256"] == state(s3)["manifest_sha256"]


def test_changed_manifest_is_ignored_once_scheduled(runner, adapter, submit, s3, tmp_path):
    submit()
    run(runner, BEFORE, tmp_path)
    sent_with = state(s3)["posts"]["youtube"]["manifest_sha256"]
    submit(title="Pasta in nine minutes")
    run(runner, BEFORE, tmp_path)
    assert len(adapter.tasks) == 1
    adapter.behaviour = lambda task: dataclasses.replace(task.state, status=Status.PUBLISHED)
    run(runner, PUBLISH_AT, tmp_path)
    post = state(s3)["posts"]["youtube"]
    assert post["status"] == "published"
    assert post["manifest_sha256"] == sent_with != state(s3)["manifest_sha256"]


def test_changed_manifest_is_ignored_after_publication(runner, adapter, submit, s3, tmp_path):
    adapter.behaviour = lambda task: dataclasses.replace(task.state, status=Status.PUBLISHED)
    submit()
    run(runner, PUBLISH_AT, tmp_path)
    submit(title="Pasta in nine minutes")
    run(runner, PUBLISH_AT, tmp_path)
    assert len(adapter.tasks) == 1
    assert state(s3)["posts"]["youtube"]["manifest_sha256"] != state(s3)["manifest_sha256"]


def test_unknown_account_is_rejected_without_the_adapter(runner, adapter, submit, s3, tmp_path):
    submit(account="other")
    run(runner, BEFORE, tmp_path)
    run(runner, BEFORE, tmp_path)
    assert adapter.tasks == []
    post = state(s3)["posts"]["youtube"]
    assert post["status"] == "rejected"
    assert "not configured" in post["error"]
    assert ("videos", VIDEO_KEY) in s3.objects


def test_rejected_post_is_retried_after_a_new_manifest(runner, adapter, submit, s3, tmp_path):
    submit(account="other")
    run(runner, BEFORE, tmp_path)
    submit()
    run(runner, BEFORE, tmp_path)
    assert state(s3)["posts"]["youtube"]["status"] == "scheduled"
    assert state(s3)["posts"]["youtube"]["error"] is None


def test_adapter_exception_fails_the_post_and_is_retried(runner, adapter, submit, s3, tmp_path):
    def boom(task):
        raise RuntimeError("quota exceeded")

    adapter.behaviour = boom
    submit()
    run(runner, BEFORE, tmp_path)
    post = state(s3)["posts"]["youtube"]
    assert post["status"] == "failed"
    assert post["error"] == "RuntimeError: quota exceeded"
    assert post["failures"] == 1
    run(runner, BEFORE, tmp_path)
    assert len(adapter.tasks) == 1
    run(runner, BEFORE + timedelta(minutes=1), tmp_path)
    assert len(adapter.tasks) == 2


def test_retry_delay_doubles_up_to_an_hour(runner, adapter, submit, s3, tmp_path):
    def boom(task):
        raise RuntimeError("quota exceeded")

    adapter.behaviour = boom
    submit()
    for minute in range(4 * 60):
        run(runner, BEFORE + timedelta(minutes=minute), tmp_path)
    times = [task.now for task in adapter.tasks]
    gaps = [(later - earlier) / timedelta(minutes=1) for earlier, later in zip(times, times[1:])]
    assert gaps[:8] == [1, 2, 4, 8, 16, 32, 60, 60]
    assert state(s3)["posts"]["youtube"]["failures"] == len(adapter.tasks)


def test_changed_manifest_retries_a_failed_post_at_once(runner, adapter, submit, tmp_path):
    def boom(task):
        raise RuntimeError("quota exceeded")

    adapter.behaviour = boom
    submit()
    run(runner, BEFORE, tmp_path)
    submit(title="Pasta in eight minutes")
    run(runner, BEFORE, tmp_path)
    assert [task.post.title for task in adapter.tasks] == ["Pasta in ten minutes", "Pasta in eight minutes"]


def test_success_resets_the_failures(runner, adapter, submit, s3, tmp_path):
    def boom(task):
        raise RuntimeError("quota exceeded")

    adapter.behaviour = boom
    submit()
    run(runner, BEFORE, tmp_path)
    adapter.behaviour = FakeAdapter().behaviour
    run(runner, BEFORE + timedelta(minutes=1), tmp_path)
    post = state(s3)["posts"]["youtube"]
    assert (post["status"], post["failures"], post["error"]) == ("scheduled", 0, None)


def test_adapter_exception_keeps_the_checkpoint_fields(runner, adapter, submit, s3, tmp_path):
    def interrupted(task):
        task.checkpoint(dataclasses.replace(task.state, status=Status.IN_PROGRESS, extra={"uploading": True}))
        raise ConnectionError("reset")

    adapter.behaviour = interrupted
    submit()
    run(runner, BEFORE, tmp_path)
    post = state(s3)["posts"]["youtube"]
    assert post["status"] == "failed"
    assert post["uploading"] is True
    run(runner, BEFORE + timedelta(minutes=1), tmp_path)
    assert adapter.tasks[-1].state.extra == {"uploading": True}


def test_checkpoint_writes_the_state_at_once(runner, adapter, submit, s3, tmp_path):
    seen = []

    def upload(task):
        task.checkpoint(dataclasses.replace(task.state, status=Status.IN_PROGRESS))
        seen.append(state(s3)["posts"]["youtube"]["status"])
        return dataclasses.replace(task.state, status=Status.SCHEDULED)

    adapter.behaviour = upload
    submit()
    run(runner, BEFORE, tmp_path)
    assert seen == ["in_progress"]
    assert state(s3)["posts"]["youtube"]["status"] == "scheduled"


def test_waiting_adapter_writes_nothing(runner, adapter, submit, s3, tmp_path):
    adapter.behaviour = lambda task: task.state
    submit()
    writes = len(s3.writes)
    run(runner, BEFORE, tmp_path)
    run(runner, BEFORE, tmp_path)
    assert len(adapter.tasks) == 2
    assert s3.writes[writes:] == [STATE_KEY]
    assert state(s3)["posts"]["youtube"]["status"] == "pending"
    assert ("videos", VIDEO_KEY) in s3.objects


def test_invalid_manifest_is_rejected_as_a_whole(runner, adapter, s3, tmp_path):
    s3.put_object(Bucket="videos", Key=f"my-project/manifests/{ENTRY_ID}.json", Body=b'{"version": 2}')
    run(runner, BEFORE, tmp_path)
    assert adapter.tasks == []
    assert state(s3)["error"].startswith("missing fields")


def test_state_is_read_back_after_a_restart(bucket, adapter, submit, s3, tmp_path):
    submit()
    run(ProjectRunner(bucket, {"youtube": adapter}, {"youtube": {"my-youtube"}}), BEFORE, tmp_path)
    restarted = ProjectRunner(bucket, {"youtube": adapter}, {"youtube": {"my-youtube"}})
    run(restarted, BEFORE, tmp_path)
    assert len(adapter.tasks) == 1


def test_task_gives_the_video_as_file_and_url(runner, adapter, submit, tmp_path):
    seen = {}

    def look(task):
        seen["file"] = task.video.file().read_bytes()
        seen["url"] = task.video.url(3600)
        return task.state

    adapter.behaviour = look
    submit()
    run(runner, BEFORE, tmp_path)
    assert seen == {"file": b"video", "url": f"https://signed.example/{VIDEO_KEY}?expires=3600"}


def test_task_gives_the_next_publication_time_of_the_account(bucket, adapter, tmp_path):
    video = tmp_path / "pasta.mp4"
    video.write_bytes(b"video")
    for entry_id, hours, account in [("a", 0, "my-youtube"), ("b", 12, "my-youtube"), ("c", 6, "second")]:
        posts = [YouTube(account=account, title=entry_id)]
        bucket.submit(Entry(id=entry_id, publish_at=PUBLISH_AT + timedelta(hours=hours), posts=posts), video)
    runner = ProjectRunner(bucket, {"youtube": adapter}, {"youtube": {"my-youtube", "second"}})
    run(runner, BEFORE, tmp_path)
    assert {task.entry.id: task.next_publish_at for task in adapter.tasks} == {
        "a": PUBLISH_AT + timedelta(hours=12), "b": None, "c": None,
    }


def test_missing_video_fails_the_post(runner, adapter, submit, s3, tmp_path):
    adapter.behaviour = lambda task: (task.video.file(), task.state)[1]
    submit()
    del s3.objects[("videos", VIDEO_KEY)]
    run(runner, BEFORE, tmp_path)
    post = state(s3)["posts"]["youtube"]
    assert post["status"] == "failed"
    assert "does not exist" in post["error"]
