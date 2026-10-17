"""The bucket shared by producers and the service: S3 access and the key layout of a project
(see docs/bucket.md).

Only module that knows the keys; the variables it reads are listed in docs/environment.md.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Self

import boto3
from botocore.exceptions import ClientError
from dotenv import find_dotenv, load_dotenv

from postillon.entry import ENTRY_ID, Entry

PROJECT = re.compile(r"[a-z0-9-]+")


class Bucket:
    """One project's view of the bucket."""

    def __init__(self, client, name: str, project: str):
        if not PROJECT.fullmatch(project):
            raise ValueError(f"project {project!r} must match {PROJECT.pattern}")
        self.client = client
        self.name = name
        self.project = project

    @classmethod
    def from_env(cls, project: str) -> Self:
        """The project's bucket, reached with the environment variables; raises ValueError if one is missing."""
        return cls(*connect_from_env(), project)

    def manifest_key(self, entry_id: str) -> str:
        return f"{self.project}/manifests/{entry_id}.json"

    def video_key(self, entry_id: str) -> str:
        return f"{self.project}/videos/{entry_id}.mp4"

    def state_key(self, entry_id: str) -> str:
        return f"{self.project}/states/{entry_id}.json"

    def submit(self, entry: Entry, video: Path) -> None:
        """Uploads the video, then writes the manifest; raises ValueError on an invalid entry
        or a missing or non-MP4 video, before writing anything."""
        manifest = entry.to_manifest()
        if not video.is_file():
            raise ValueError(f"video {video} does not exist")
        if video.suffix.lower() != ".mp4":
            raise ValueError(f"video {video} is not an MP4 file")
        # The video goes first: a manifest the service discovers always finds its video.
        self.client.upload_file(
            str(video), self.name, self.video_key(entry.id), ExtraArgs={"ContentType": "video/mp4"},
        )
        self.client.put_object(
            Bucket=self.name, Key=self.manifest_key(entry.id), Body=manifest, ContentType="application/json",
        )

    def list_manifests(self) -> dict[str, str]:
        """The ETag of each manifest of the project, by entry; keys outside the entry alphabet are left out."""
        prefix = f"{self.project}/manifests/"
        manifests = {}
        for page in self.client.get_paginator("list_objects_v2").paginate(Bucket=self.name, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                entry_id = key.removeprefix(prefix).removesuffix(".json")
                if key.endswith(".json") and ENTRY_ID.fullmatch(entry_id):
                    manifests[entry_id] = obj["ETag"]
        return manifests

    def read_manifest(self, entry_id: str) -> bytes | None:
        return self._read(self.manifest_key(entry_id))

    def read_state(self, entry_id: str) -> bytes | None:
        return self._read(self.state_key(entry_id))

    def write_state(self, entry_id: str, raw: bytes) -> None:
        self.client.put_object(
            Bucket=self.name, Key=self.state_key(entry_id), Body=raw, ContentType="application/json",
        )

    def download_video(self, entry_id: str, path: Path) -> None:
        """Downloads the entry's video to `path`; raises ValueError if the bucket has none."""
        try:
            self.client.download_file(self.name, self.video_key(entry_id), str(path))
        except ClientError as e:
            if _missing(e):
                raise ValueError(f"video {self.video_key(entry_id)} does not exist") from None
            raise

    def video_url(self, entry_id: str, expires_seconds: int) -> str:
        """A signed URL that reads the entry's video without credentials until it expires."""
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.name, "Key": self.video_key(entry_id)}, ExpiresIn=expires_seconds,
        )

    def delete_video(self, entry_id: str) -> None:
        self.client.delete_object(Bucket=self.name, Key=self.video_key(entry_id))

    def _read(self, key: str) -> bytes | None:
        try:
            return self.client.get_object(Bucket=self.name, Key=key)["Body"].read()
        except ClientError as e:
            if _missing(e):
                return None
            raise


def connect_from_env():
    """The S3 client and the bucket name read from the environment; raises ValueError if a variable is missing."""
    load_dotenv(find_dotenv(usecwd=True))
    client = boto3.client(
        "s3",
        endpoint_url=_env("POSTILLON_S3_ENDPOINT"),
        aws_access_key_id=_env("POSTILLON_S3_ACCESS_KEY_ID"),
        aws_secret_access_key=_env("POSTILLON_S3_SECRET_ACCESS_KEY"),
        # R2 ignores the region but the S3 client requires one; "auto" is what R2 documents.
        region_name="auto",
    )
    return client, _env("POSTILLON_BUCKET")


def _missing(error: ClientError) -> bool:
    return error.response.get("Error", {}).get("Code") in ("NoSuchKey", "404")


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"environment variable {name} is not set")
    return value
