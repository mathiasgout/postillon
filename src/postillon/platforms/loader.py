"""The clients of the configured platforms, each imported only when an account of its platform
is configured, so that a missing extra matters only where it is used."""

from __future__ import annotations

from pathlib import Path

from postillon.platforms.base import Platform
from postillon.settings import ProjectSettings


def load_platforms(project: ProjectSettings, data_dir: Path) -> dict[str, Platform]:
    """The client of each platform with an account in the project; raises ValueError when a
    platform's extra or an account's secret is missing."""
    platforms: dict[str, Platform] = {}
    if project.youtube:
        try:
            from postillon.platforms.youtube.client import YouTubePlatform  # noqa: PLC0415 (optional extra)
        except ModuleNotFoundError as e:
            raise ValueError(f"youtube: client unavailable ({e.name} missing), install postillon[youtube]") from None
        platforms["youtube"] = YouTubePlatform(project.youtube)
    if project.instagram:
        from postillon.platforms.instagram.client import InstagramPlatform  # noqa: PLC0415 (loaded with its peer)

        platforms["instagram"] = InstagramPlatform(project.instagram, data_dir / "instagram-tokens.json")
    return platforms
