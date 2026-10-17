"""An entry and its manifest, the JSON a producer writes and the service reads (see docs/manifest.md).

Only module that converts between the two; it talks to no bucket and no platform.
"""

from __future__ import annotations

import dataclasses
import json
import re
from datetime import UTC, datetime
from typing import Self

from postillon.platforms import POSTS, Post

MANIFEST_VERSION = 1
ENTRY_ID = re.compile(r"[a-z0-9_-]+(/[a-z0-9_-]+)*")
MANIFEST_FIELDS = {"version", "publish_at", "posts"}


@dataclasses.dataclass(frozen=True)
class Entry:
    id: str
    publish_at: datetime
    posts: list[Post]

    def validate(self) -> None:
        """Raises ValueError if the entry or one of its posts breaks its rules."""
        if not ENTRY_ID.fullmatch(self.id):
            raise ValueError(f"entry id {self.id!r} must match {ENTRY_ID.pattern}")
        if self.publish_at.tzinfo is None:
            raise ValueError("publish_at has no time zone")
        if not self.posts:
            raise ValueError("entry has no post")
        names = [post.name for post in self.posts]
        for post in self.posts:
            if POSTS.get(post.name) is not type(post):
                raise ValueError(f"unknown platform {post.name!r}")
            if names.count(post.name) > 1:
                raise ValueError(f"platform {post.name!r} appears twice")
            post.validate()

    def to_manifest(self) -> bytes:
        """The manifest of the validated entry; raises ValueError like `validate`."""
        self.validate()
        data = {
            "version": MANIFEST_VERSION,
            "publish_at": self.publish_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "posts": {post.name: post.to_dict() for post in self.posts},
        }
        return json.dumps(data, indent=2, ensure_ascii=False).encode()

    @classmethod
    def from_manifest(cls, entry_id: str, raw: bytes) -> Self:
        """The validated entry read from its manifest; raises ValueError on any breach of the format."""
        try:
            data = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise ValueError(f"manifest is not valid JSON: {e}") from None
        if not isinstance(data, dict):
            raise ValueError("manifest must be a JSON object")
        unknown = sorted(set(data) - MANIFEST_FIELDS)
        if unknown:
            raise ValueError(f"unknown fields {unknown}")
        missing = sorted(MANIFEST_FIELDS - set(data))
        if missing:
            raise ValueError(f"missing fields {missing}")
        if data["version"] != MANIFEST_VERSION:
            raise ValueError(f"unknown manifest version {data['version']!r}")
        publish_at = data["publish_at"]
        if not isinstance(publish_at, str) or not publish_at.endswith("Z"):
            raise ValueError("publish_at must be RFC 3339 in UTC, with the Z suffix")
        try:
            when = datetime.fromisoformat(publish_at)
        except ValueError:
            raise ValueError(f"publish_at {publish_at!r} is not RFC 3339") from None
        posts = data["posts"]
        if not isinstance(posts, dict):
            raise ValueError("posts must be a JSON object")
        parsed = []
        for name, post in posts.items():
            if name not in POSTS:
                raise ValueError(f"unknown platform {name!r}")
            parsed.append(POSTS[name].from_dict(post))
        entry = cls(id=entry_id, publish_at=when, posts=parsed)
        entry.validate()
        return entry
