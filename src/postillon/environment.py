"""The process environment, completed by a `.env` file found from the working directory
upwards (see docs/environment.md).

Only module that reads `.env`, which postillon never writes; the variables themselves are
named by the bucket and by each platform's document.
"""

from __future__ import annotations

import os

from dotenv import find_dotenv, load_dotenv


def load() -> None:
    """Adds the variables of `.env` to the environment, without overriding those already set."""
    load_dotenv(find_dotenv(usecwd=True))


def variable(name: str) -> str:
    """The variable's value; raises ValueError if it is not set."""
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"environment variable {name} is not set")
    return value

