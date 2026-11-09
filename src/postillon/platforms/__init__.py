"""The platforms postillon knows, each declared once by its package (see docs/add-a-platform.md).

Loads the posts and the account settings only, without any platform SDK; `loader` builds the clients.
"""

from __future__ import annotations

from typing import Any

from postillon.platforms import instagram, tiktok, youtube
from postillon.platforms.base import PlatformSpec

# In the order an entry lists its posts.
PLATFORMS: dict[str, PlatformSpec[Any]] = {
    spec.name: spec for spec in (youtube.PLATFORM, instagram.PLATFORM, tiktok.PLATFORM)
}
