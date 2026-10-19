"""The TikTok post and its rules (see docs/tiktok.md)."""

from __future__ import annotations

from typing import ClassVar

from pydantic import field_validator

from postillon.platforms.base import PlatformPost

# The limit of the Content Posting API, in UTF-16 code units, rather than the larger one of
# TikTok Studio: a post stays valid for an adapter that publishes through the API.
CAPTION_UTF16_UNITS = 2200


class TikTokPost(PlatformPost):
    name: ClassVar[str] = "tiktok"
    manual: ClassVar[bool] = True

    caption: str = ""

    @field_validator("caption")
    @classmethod
    def _caption_fits(cls, caption: str) -> str:
        units = len(caption.encode("utf-16-le")) // 2
        if units > CAPTION_UTF16_UNITS:
            raise ValueError(f"caption is {units} UTF-16 units, limit {CAPTION_UTF16_UNITS}")
        return caption
