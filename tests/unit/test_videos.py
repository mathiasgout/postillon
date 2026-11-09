import hashlib

import pytest

from postillon.errors import VideoNotMp4, VideoTooLarge
from postillon.storage.videos import StoredVideo, VideoStore
from tests.support import MP4, FakeBucket, stage


def test_received_video_is_hashed_then_promoted_under_its_digest(videos: VideoStore):
    staged = stage(videos)
    assert (staged.size, staged.sha256) == (len(MP4), hashlib.sha256(MP4).hexdigest())
    videos.promote(staged, "my-project", "day-23")
    assert videos.path("my-project", "day-23", staged.sha256).read_bytes() == MP4
    assert not staged.path.exists()


def test_a_new_video_keeps_the_previous_file_until_deleted(videos: VideoStore):
    first = stage(videos)
    videos.promote(first, "my-project", "day")
    with videos.path("my-project", "day", first.sha256).open("rb") as opened:
        videos.promote(stage(videos, MP4 + b"new"), "my-project", "day")
        videos.delete("my-project", "day", first.sha256)
        assert opened.read() == MP4


@pytest.mark.parametrize(
    ("chunks", "error"),
    [
        ([b"\x00\x00\x00\x18moovmp42" + b"\x00" * 64], VideoNotMp4),
        ([b"\x00\x00", b"\x00\x18moov"], VideoNotMp4),
        ([b"\x00\x00\x00"], VideoNotMp4),
        ([MP4, b"\x00" * 10_000], VideoTooLarge),
    ],
)
def test_refused_video_leaves_no_file(videos: VideoStore, chunks: list[bytes], error: type[Exception]):
    with pytest.raises(error):
        receive(videos, chunks)
    assert list(videos.root.rglob("*.mp4")) == []


def receive(videos: VideoStore, chunks: list[bytes]) -> None:
    with videos.upload() as upload:
        for chunk in chunks:
            upload.write(chunk)
        upload.finish()


def test_signature_split_across_chunks_is_read(videos: VideoStore):
    with videos.upload() as upload:
        for chunk in (MP4[:3], MP4[3:6], MP4[6:]):
            upload.write(chunk)
        assert upload.finish().size == len(MP4)


def test_stored_video_uploads_to_the_bucket_for_a_url(videos: VideoStore):
    bucket = FakeBucket()
    staged = stage(videos)
    videos.promote(staged, "my-project", "day")
    video = StoredVideo(videos, bucket, "my-project", "day", staged.sha256)  # type: ignore[arg-type]
    assert video.file() == videos.path("my-project", "day", staged.sha256)
    assert video.url(3600) == "https://signed.example/my-project/day.mp4?expires=3600"
    assert bucket.videos == {("my-project", "day")}


@pytest.mark.parametrize(("sha256", "message"), [(None, "holds no video"), ("0" * 64, "does not exist")])
def test_stored_video_without_file_raises(videos: VideoStore, sha256: str | None, message: str):
    with pytest.raises(ValueError, match=message):
        StoredVideo(videos, FakeBucket(), "my-project", "day", sha256).file()  # type: ignore[arg-type]
