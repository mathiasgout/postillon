"""The daily check of the platform credentials that expire (see docs/run-the-service.md).

Runs whether or not a post waits, so that an idle account still warns before its access ends.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from postillon.platforms.base import ChecksCredentials, Platform


def check_credentials(platforms: Mapping[str, Mapping[str, Platform]], now: datetime) -> None:
    for clients in platforms.values():
        for client in clients.values():
            if isinstance(client, ChecksCredentials):
                client.check_credentials(now)
