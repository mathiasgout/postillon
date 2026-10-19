"""The settings of an Instagram account in the configuration (see docs/instagram.md)."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints


class InstagramAccount(BaseModel):
    """One professional account, authorized by a long-lived token whose variable the account names."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    username: Annotated[str, StringConstraints(pattern=r"^[\w.]+$")]
    access_token_env: Annotated[str, StringConstraints(pattern=r"^[A-Z_][A-Z0-9_]*$")]
