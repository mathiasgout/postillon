"""The Instagram post, a Reel, and its rules (see docs/instagram.md)."""

from __future__ import annotations

import re
from typing import Annotated, ClassVar

from pydantic import Field, StringConstraints, field_validator

from postillon.platforms.base import PlatformPost

# Limits of a Reel caption in the Instagram API.
CAPTION_CHARS = 2200
HASHTAGS = 30
MENTIONS = 20
HASHTAG = re.compile(r"(?<!\w)#\w+")
MENTION = re.compile(r"(?<!\w)@[\w.]+")


class InstagramPost(PlatformPost):
    name: ClassVar[str] = "instagram"

    caption: Annotated[str, StringConstraints(max_length=CAPTION_CHARS)] = ""
    share_to_feed: bool = True
    # The frame used as cover, in milliseconds from the start.
    thumb_offset: Annotated[int, Field(ge=0)] = 0

    @field_validator("caption")
    @classmethod
    def _caption_tags_fit(cls, caption: str) -> str:
        hashtags = len(HASHTAG.findall(caption))
        if hashtags > HASHTAGS:
            raise ValueError(f"caption has {hashtags} hashtags, limit {HASHTAGS}")
        mentions = len(MENTION.findall(caption))
        if mentions > MENTIONS:
            raise ValueError(f"caption has {mentions} mentions, limit {MENTIONS}")
        return caption
