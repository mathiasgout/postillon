"""The clients of the configured platforms, each imported only when an account of its platform
is configured, so that a missing extra matters only where it is used."""

from __future__ import annotations

from postillon.platforms import PLATFORMS
from postillon.platforms.base import Platform
from postillon.settings import ProjectSettings


def load_platforms(project: ProjectSettings) -> dict[str, Platform]:
    """The client of each platform with an account in the project; raises ValueError when a
    platform's extra or an account's secret is missing."""
    platforms: dict[str, Platform] = {}
    for name, spec in PLATFORMS.items():
        accounts = project.account_settings(name)
        if not accounts:
            continue
        try:
            platforms[name] = spec.client(accounts)
        except ModuleNotFoundError as e:
            if spec.extra is None:
                raise
            missing = f"{name}: client unavailable ({e.name} missing)"
            raise ValueError(f"{missing}, install postillon[{spec.extra}]") from None
    return platforms
