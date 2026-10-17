"""The YouTube post and its rules (see docs/youtube.md)."""

from __future__ import annotations

import dataclasses

from postillon.platforms.base import Post

# Limits of the YouTube Data API v3: a title counts characters, a description bytes.
TITLE_CHARS = 100
DESCRIPTION_BYTES = 5000
FORBIDDEN = ("<", ">")


@dataclasses.dataclass(frozen=True, kw_only=True)
class YouTube(Post):
    name = "youtube"

    title: str
    description: str = ""
    category_id: str = "22"
    made_for_kids: bool = False
    contains_synthetic_media: bool = False
    video_id: str | None = None

    def validate(self) -> None:
        super().validate()
        for field in ("title", "description", "category_id"):
            if not isinstance(getattr(self, field), str):
                raise ValueError(f"youtube: {field} must be a string")
        for field in ("made_for_kids", "contains_synthetic_media"):
            if not isinstance(getattr(self, field), bool):
                raise ValueError(f"youtube: {field} must be a boolean")
        if self.video_id is not None and not (isinstance(self.video_id, str) and self.video_id):
            raise ValueError("youtube: video_id must be a non-empty string")
        if not self.title.strip():
            raise ValueError("youtube: title is empty")
        if len(self.title) > TITLE_CHARS:
            raise ValueError(f"youtube: title is {len(self.title)} characters, limit {TITLE_CHARS}")
        size = len(self.description.encode())
        if size > DESCRIPTION_BYTES:
            raise ValueError(f"youtube: description is {size} bytes, limit {DESCRIPTION_BYTES}")
        for field in ("title", "description"):
            if any(c in getattr(self, field) for c in FORBIDDEN):
                raise ValueError(f"youtube: {field} contains < or >")
        if not self.category_id.isdigit():
            raise ValueError(f"youtube: category_id {self.category_id!r} is not a number")
