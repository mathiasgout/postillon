"""The Instagram post, a Reel, and its rules (see docs/instagram.md)."""

from __future__ import annotations

import dataclasses
import re

from postillon.platforms.base import Post

# Limits of a Reel caption in the Instagram API.
CAPTION_CHARS = 2200
HASHTAGS = 30
MENTIONS = 20
HASHTAG = re.compile(r"(?<!\w)#\w+")
MENTION = re.compile(r"(?<!\w)@[\w.]+")


@dataclasses.dataclass(frozen=True, kw_only=True)
class Instagram(Post):
    name = "instagram"

    caption: str = ""
    share_to_feed: bool = True
    thumb_offset: int = 0

    def validate(self) -> None:
        super().validate()
        if not isinstance(self.caption, str):
            raise ValueError("instagram: caption must be a string")
        if not isinstance(self.share_to_feed, bool):
            raise ValueError("instagram: share_to_feed must be a boolean")
        if not isinstance(self.thumb_offset, int) or isinstance(self.thumb_offset, bool) or self.thumb_offset < 0:
            raise ValueError("instagram: thumb_offset must be a non-negative integer of milliseconds")
        if len(self.caption) > CAPTION_CHARS:
            raise ValueError(f"instagram: caption is {len(self.caption)} characters, limit {CAPTION_CHARS}")
        hashtags = len(HASHTAG.findall(self.caption))
        if hashtags > HASHTAGS:
            raise ValueError(f"instagram: caption has {hashtags} hashtags, limit {HASHTAGS}")
        mentions = len(MENTION.findall(self.caption))
        if mentions > MENTIONS:
            raise ValueError(f"instagram: caption has {mentions} mentions, limit {MENTIONS}")
