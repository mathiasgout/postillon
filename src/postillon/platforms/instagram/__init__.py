"""Instagram: its declaration, post and account settings here, its client in `client`."""

from __future__ import annotations

from collections.abc import Mapping

from postillon.platforms.base import Platform, PlatformSpec
from postillon.platforms.instagram.post import InstagramPost
from postillon.platforms.instagram.settings import InstagramAccount


def _client(accounts: Mapping[str, InstagramAccount]) -> Platform:
    from postillon.platforms.instagram.client import InstagramPlatform  # noqa: PLC0415 (loaded by the worker only)

    return InstagramPlatform(accounts)


PLATFORM = PlatformSpec(name="instagram", post=InstagramPost, account=InstagramAccount, client=_client)

__all__ = ["PLATFORM", "InstagramAccount", "InstagramPost"]
