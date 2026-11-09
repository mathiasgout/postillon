"""YouTube: its declaration, post and account settings here, its client in `client`, behind the
`youtube` extra."""

from __future__ import annotations

from collections.abc import Mapping

from postillon.platforms.base import Platform, PlatformSpec
from postillon.platforms.youtube.post import YouTubePost
from postillon.platforms.youtube.settings import YouTubeAccount


def _client(accounts: Mapping[str, YouTubeAccount]) -> Platform:
    from postillon.platforms.youtube.client import YouTubePlatform  # noqa: PLC0415 (behind the extra)

    return YouTubePlatform(accounts)


PLATFORM = PlatformSpec(name="youtube", post=YouTubePost, account=YouTubeAccount, client=_client, extra="youtube")

__all__ = ["PLATFORM", "YouTubeAccount", "YouTubePost"]
