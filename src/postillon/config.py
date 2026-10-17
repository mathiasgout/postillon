"""The service configuration: the projects it serves and, per platform, their accounts
(see docs/configuration.md).

The core checks names only; each adapter checks the settings of its own accounts.
"""

from __future__ import annotations

import dataclasses
import tomllib
from pathlib import Path
from typing import Any

from postillon.bucket import PROJECT
from postillon.platforms import POSTS
from postillon.platforms.base import ACCOUNT

DEFAULT_POLL_SECONDS = 60

# Project, then platform, then account, then the account's settings.
Projects = dict[str, dict[str, dict[str, dict[str, Any]]]]


@dataclasses.dataclass(frozen=True)
class Config:
    poll_seconds: int
    projects: Projects


def load_config(path: Path) -> Config:
    """The configuration read from a TOML file; raises ValueError on an unknown key or name."""
    try:
        data = tomllib.loads(path.read_text())
    except FileNotFoundError:
        raise ValueError(f"configuration {path} does not exist") from None
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"configuration {path} is not valid TOML: {e}") from None
    unknown = sorted(set(data) - {"poll_seconds", "projects"})
    if unknown:
        raise ValueError(f"unknown configuration keys {unknown}")
    poll_seconds = data.get("poll_seconds", DEFAULT_POLL_SECONDS)
    if not isinstance(poll_seconds, int) or isinstance(poll_seconds, bool) or poll_seconds < 1:
        raise ValueError("poll_seconds must be a positive integer")
    projects = data.get("projects")
    if not isinstance(projects, dict) or not projects:
        raise ValueError("configuration declares no project")
    for project, platforms in projects.items():
        if not PROJECT.fullmatch(project):
            raise ValueError(f"project {project!r} must match {PROJECT.pattern}")
        for platform, accounts in _table(platforms, project).items():
            if platform not in POSTS:
                raise ValueError(f"{project}: unknown platform {platform!r}")
            for account, settings in _table(accounts, f"{project}.{platform}").items():
                if not ACCOUNT.fullmatch(account):
                    raise ValueError(f"{project}.{platform}: account {account!r} must match {ACCOUNT.pattern}")
                _table(settings, f"{project}.{platform}.{account}")
    return Config(poll_seconds=poll_seconds, projects=projects)


def _table(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{where} must be a table")
    return value
