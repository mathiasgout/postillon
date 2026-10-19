import io
from pathlib import Path

import pytest

from postillon.storage.videos import InvalidVideo, StoredVideo, VideoStore
from tests.support import MP4, FakeBucket


def test_staged_video_is_promoted_in_place(videos: VideoStore):
    staged = videos.stage(io.BytesIO(MP4))
    videos.promote(staged, "my-project", "season-1/day-23")
    assert videos.path("my-project", "season-1/day-23").read_bytes() == MP4
    assert not staged.exists()


def test_promotion_keeps_an_open_file_readable(videos: VideoStore):
    videos.promote(videos.stage(io.BytesIO(MP4)), "my-project", "day")
    with videos.path("my-project", "day").open("rb") as opened:
        videos.promote(videos.stage(io.BytesIO(MP4 + b"new")), "my-project", "day")
        assert opened.read() == MP4
    assert videos.path("my-project", "day").read_bytes() == MP4 + b"new"


@pytest.mark.parametrize(
    ("content", "message"),
    [(b"\x00\x00\x00\x18moovmp42" + b"\x00" * 64, "not an MP4"), (MP4 + b"\x00" * 10_000, "over 10000 bytes")],
)
def test_invalid_video_leaves_no_file(videos: VideoStore, settings_videos_dir: Path, content: bytes, message: str):
    with pytest.raises(InvalidVideo, match=message):
        videos.stage(io.BytesIO(content))
    assert list(settings_videos_dir.rglob("*.mp4")) == []


@pytest.fixture
def settings_videos_dir(videos: VideoStore) -> Path:
    return videos.root


def test_stored_video_uploads_to_the_bucket_for_a_url(videos: VideoStore):
    bucket = FakeBucket()
    videos.promote(videos.stage(io.BytesIO(MP4)), "my-project", "day")
    video = StoredVideo(videos, bucket, "my-project", "day")  # type: ignore[arg-type]
    assert video.file() == videos.path("my-project", "day")
    assert video.url(3600) == "https://signed.example/my-project/day.mp4?expires=3600"
    assert bucket.videos == {("my-project", "day")}


def test_stored_video_without_file_raises(videos: VideoStore):
    with pytest.raises(ValueError, match="does not exist"):
        StoredVideo(videos, FakeBucket(), "my-project", "day").file()  # type: ignore[arg-type]
