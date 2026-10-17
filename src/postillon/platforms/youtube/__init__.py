"""YouTube: the post in `post`, which producers use; the adapter that talks to YouTube lives
apart, behind the `youtube` extra."""

from postillon.platforms.youtube.post import YouTube

__all__ = ["YouTube"]
