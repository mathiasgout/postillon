from pathlib import Path
from typing import Any

from botocore.exceptions import ClientError

from postillon.storage.bucket import Bucket


class FakeS3:
    """The calls of boto3's S3 client that the bucket makes, over a dict of objects and their metadata."""

    def __init__(self) -> None:
        self.objects: dict[str, dict[str, str]] = {}
        self.uploads: list[str] = []

    def head_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {"Metadata": self.objects[Key]}

    def upload_file(self, path: str, bucket: str, key: str, ExtraArgs: dict[str, Any]) -> None:
        self.objects[key] = ExtraArgs["Metadata"]
        self.uploads.append(key)

    def generate_presigned_url(self, method: str, Params: dict[str, str], ExpiresIn: int) -> str:
        return f"https://signed.example/{Params['Key']}"


def test_the_copy_is_uploaded_again_when_the_video_changes(tmp_path: Path):
    s3 = FakeS3()
    bucket = Bucket(s3, "videos")
    path = tmp_path / "day.mp4"
    path.write_bytes(b"video")
    for sha256 in ("a" * 64, "a" * 64, "b" * 64):
        assert (
            bucket.video_url("my-project", "day", path, sha256, 60)
            == "https://signed.example/my-project/videos/day.mp4"
        )
    assert s3.uploads == ["my-project/videos/day.mp4", "my-project/videos/day.mp4"]
    assert s3.objects["my-project/videos/day.mp4"] == {"sha256": "b" * 64}
