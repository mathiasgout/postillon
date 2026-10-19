"""The daily renewal of the platform credentials that expire unless renewed (see docs/run-the-service.md).

Runs whether or not a post waits, so that an account idle for weeks keeps valid credentials.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from postillon.platforms.base import Platform, RenewsCredentials


def renew_credentials(platforms: Mapping[str, Mapping[str, Platform]], now: datetime) -> None:
    for clients in platforms.values():
        for client in clients.values():
            if isinstance(client, RenewsCredentials):
                client.renew_credentials(now)
