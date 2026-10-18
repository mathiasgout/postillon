"""The process environment, completed by a `.env` file found from the working directory
upwards (see docs/environment.md).

Only module that reads or writes `.env`; the variables themselves are named by the bucket
and by each platform's document.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv, set_key


def load() -> None:
    """Adds the variables of `.env` to the environment, without overriding those already set."""
    load_dotenv(find_dotenv(usecwd=True))


def variable(name: str) -> str:
    """The variable's value; raises ValueError if it is not set."""
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"environment variable {name} is not set")
    return value


def save(name: str, value: str) -> Path:
    """Writes the variable to `.env`, created readable by its owner only, and returns the file's path."""
    path = Path(find_dotenv(usecwd=True) or ".env")
    path.touch(mode=0o600, exist_ok=True)
    set_key(path, name, value, quote_mode="never")
    os.environ[name] = value
    return path
