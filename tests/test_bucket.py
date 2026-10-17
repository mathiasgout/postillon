import json
from datetime import UTC, datetime

import pytest

from postillon import Bucket, Entry
from postillon.platforms.youtube import YouTube

ENTRY = Entry(
    id="season-1/day-16",
    publish_at=datetime(2026, 10, 19, 6, 0, tzinfo=UTC),
    posts=[YouTube(account="my-youtube", title="Pasta in ten minutes")],
)


class FakeS3:
    """Records the calls `submit` makes, in order."""

    def __init__(self):
        self.calls = []

    def upload_file(self, filename, bucket, key, ExtraArgs):
        self.calls.append(("upload_file", bucket, key, ExtraArgs["ContentType"]))

    def put_object(self, Bucket, Key, Body, ContentType):
        self.calls.append(("put_object", Bucket, Key, ContentType, Body))


@pytest.fixture
def s3():
    return FakeS3()


@pytest.fixture
def video(tmp_path):
    path = tmp_path / "pasta.mp4"
    path.write_bytes(b"video")
    return path


def test_keys_follow_the_project_layout(s3):
    bucket = Bucket(s3, "videos", "my-project")
    assert bucket.manifest_key("season-1/day-16") == "my-project/manifests/season-1/day-16.json"
    assert bucket.video_key("season-1/day-16") == "my-project/videos/season-1/day-16.mp4"
    assert bucket.state_key("season-1/day-16") == "my-project/states/season-1/day-16.json"


@pytest.mark.parametrize("project", ["", "My-Project", "my_project", "a/b"])
def test_invalid_projects(s3, project):
    with pytest.raises(ValueError, match="project"):
        Bucket(s3, "videos", project)


def test_submit_uploads_the_video_before_the_manifest(s3, video):
    Bucket(s3, "videos", "my-project").submit(ENTRY, video)
    upload, put = s3.calls
    assert upload == ("upload_file", "videos", "my-project/videos/season-1/day-16.mp4", "video/mp4")
    assert put[:4] == ("put_object", "videos", "my-project/manifests/season-1/day-16.json", "application/json")
    assert json.loads(put[4])["posts"]["youtube"]["title"] == "Pasta in ten minutes"


def test_submit_writes_nothing_for_an_invalid_entry(s3, video):
    invalid = Entry(id="Day 16", publish_at=ENTRY.publish_at, posts=ENTRY.posts)
    with pytest.raises(ValueError, match="entry id"):
        Bucket(s3, "videos", "my-project").submit(invalid, video)
    assert s3.calls == []


def test_submit_writes_nothing_without_the_video(s3, tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        Bucket(s3, "videos", "my-project").submit(ENTRY, tmp_path / "missing.mp4")
    assert s3.calls == []


def test_submit_refuses_a_video_that_is_not_mp4(s3, tmp_path):
    video = tmp_path / "pasta.mov"
    video.write_bytes(b"video")
    with pytest.raises(ValueError, match="not an MP4"):
        Bucket(s3, "videos", "my-project").submit(ENTRY, video)
    assert s3.calls == []


def test_from_env_names_the_missing_variable(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for name in ("POSTILLON_S3_ENDPOINT", "POSTILLON_S3_ACCESS_KEY_ID", "POSTILLON_S3_SECRET_ACCESS_KEY", "POSTILLON_BUCKET"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValueError, match="POSTILLON_S3_ENDPOINT"):
        Bucket.from_env("my-project")
