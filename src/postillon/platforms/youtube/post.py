"""The YouTube post and its rules (see docs/youtube.md)."""

from __future__ import annotations

from typing import Annotated, ClassVar

from pydantic import StringConstraints, field_validator

from postillon.platforms.base import PlatformPost

# Limits of the YouTube Data API v3: a title counts characters, a description bytes.
TITLE_CHARS = 100
DESCRIPTION_BYTES = 5000
FORBIDDEN = ("<", ">")


class YouTubePost(PlatformPost):
    name: ClassVar[str] = "youtube"

    title: Annotated[str, StringConstraints(min_length=1, max_length=TITLE_CHARS)]
    description: str = ""
    category_id: Annotated[str, StringConstraints(pattern=r"^[0-9]+$")] = "22"
    made_for_kids: bool = False
    contains_synthetic_media: bool = False

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, title: str) -> str:
        if not title.strip():
            raise ValueError("title is blank")
        return title

    @field_validator("description")
    @classmethod
    def _description_fits(cls, description: str) -> str:
        size = len(description.encode())
        if size > DESCRIPTION_BYTES:
            raise ValueError(f"description is {size} bytes, limit {DESCRIPTION_BYTES}")
        return description

    @field_validator("title", "description")
    @classmethod
    def _no_angle_brackets(cls, text: str) -> str:
        if any(c in text for c in FORBIDDEN):
            raise ValueError("contains < or >")
        return text
