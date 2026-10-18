"""The platforms postillon knows, by the name their post carries in a manifest."""

from __future__ import annotations

from postillon.platforms.base import Post
from postillon.platforms.instagram import Instagram
from postillon.platforms.youtube import YouTube

POSTS: dict[str, type[Post]] = {post.name: post for post in (YouTube, Instagram)}
