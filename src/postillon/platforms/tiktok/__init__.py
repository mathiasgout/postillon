"""TikTok: its declaration, post and account settings here, its client in `client`."""

from __future__ import annotations

from collections.abc import Mapping

from postillon.platforms.base import Platform, PlatformSpec
from postillon.platforms.tiktok.post import TikTokPost
from postillon.platforms.tiktok.settings import TikTokAccount


def _client(accounts: Mapping[str, TikTokAccount]) -> Platform:
    from postillon.platforms.tiktok.client import TikTokPlatform  # noqa: PLC0415 (loaded by the worker only)

    # The service holds no credentials for a TikTok account.
    return TikTokPlatform()


PLATFORM = PlatformSpec(name="tiktok", post=TikTokPost, account=TikTokAccount, client=_client, manual=True)

__all__ = ["PLATFORM", "TikTokAccount", "TikTokPost"]
