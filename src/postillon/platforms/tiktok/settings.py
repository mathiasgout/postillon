"""The settings of a TikTok account in the configuration (see docs/tiktok.md)."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints


class TikTokAccount(BaseModel):
    """One account the operator schedules videos on; the service holds no credentials for it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    handle: Annotated[str, StringConstraints(pattern=r"^@[\w.]+$")]
