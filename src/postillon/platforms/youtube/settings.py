"""The settings of a YouTube account in the configuration (see docs/youtube.md)."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

EnvName = Annotated[str, StringConstraints(pattern=r"^[A-Z_][A-Z0-9_]*$")]


class YouTubeAccount(BaseModel):
    """One channel, authorized by a refresh token whose variable the account names."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    handle: Annotated[str, StringConstraints(pattern=r"^@[\w.-]+$")]
    refresh_token_env: EnvName
    client_id_env: EnvName = "POSTILLON_YOUTUBE_CLIENT_ID"
    client_secret_env: EnvName = "POSTILLON_YOUTUBE_CLIENT_SECRET"
