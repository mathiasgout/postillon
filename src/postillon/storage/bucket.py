"""The S3-compatible bucket (Cloudflare R2): the copy of a video a platform fetches by URL, and the
daily backups of the database (see docs/bucket.md).

Only module that knows the keys; the service is the only writer of the bucket.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError

from postillon.settings import BucketSettings

# Outside the project alphabet, so that no project prefix can collide with it.
BACKUPS = "_postillon/backups"


class Bucket:
    def __init__(self, client: Any, name: str):
        self.client = client
        self.name = name

    @classmethod
    def connect(cls, settings: BucketSettings) -> Bucket:
        client = boto3.client(
            "s3",
            endpoint_url=settings.endpoint,
            aws_access_key_id=settings.access_key_id,
            aws_secret_access_key=settings.secret_access_key.get_secret_value(),
            # R2 ignores the region but the S3 client requires one; "auto" is what R2 documents.
            region_name="auto",
        )
        return cls(client, settings.name)

    def video_url(self, project: str, key: str, path: Path, expires_seconds: int) -> str:
        """A signed URL that reads the entry's video without credentials, after uploading `path`
        when the bucket does not hold it yet."""
        object_key = _video_key(project, key)
        if not self._exists(object_key):
            self.client.upload_file(str(path), self.name, object_key, ExtraArgs={"ContentType": "video/mp4"})
        return str(
            self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.name, "Key": object_key},
                ExpiresIn=expires_seconds,
            )
        )

    def delete_video(self, project: str, key: str) -> None:
        """Deletes the entry's video, whether the bucket holds it or not."""
        self.client.delete_object(Bucket=self.name, Key=_video_key(project, key))

    def upload_backup(self, path: Path, day: date) -> None:
        """Uploads a copy of the database, one object per day."""
        self.client.upload_file(str(path), self.name, f"{BACKUPS}/{day.isoformat()}.sqlite3")

    def _exists(self, object_key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.name, Key=object_key)
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                return False
            raise
        return True


def _video_key(project: str, key: str) -> str:
    return f"{project}/videos/{key}.mp4"
