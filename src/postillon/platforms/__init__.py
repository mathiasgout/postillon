"""The platforms postillon knows, by the name their post carries in a manifest.

Loads the posts only, without any platform SDK; `loader` builds the clients.
"""

from __future__ import annotations

from postillon.platforms.base import PlatformPost
from postillon.platforms.instagram import InstagramPost
from postillon.platforms.tiktok import TikTokPost
from postillon.platforms.youtube import YouTubePost

POSTS: dict[str, type[PlatformPost]] = {post.name: post for post in (YouTubePost, InstagramPost, TikTokPost)}
