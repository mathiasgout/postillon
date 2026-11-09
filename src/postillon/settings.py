"""The service configuration: `postillon.toml` for the projects and their accounts, environment
variables for the secrets (see docs/configuration.md).

Read once at start by each process; an invalid configuration stops it before anything runs.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, SecretStr, StringConstraints, create_model
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict, TomlConfigSettingsSource

from postillon.platforms import PLATFORMS
from postillon.platforms.base import AccountName

ProjectName = Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]+$")]
CONFIG_FILE = Path("postillon.toml")


class _ProjectSettings(BaseModel):
    """The accounts of one project, by platform and account name."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    def account_settings(self, platform: str) -> dict[str, BaseModel]:
        return dict(getattr(self, platform, {}))

    def accounts(self, platform: str) -> set[str]:
        return set(self.account_settings(platform))


# A field per platform of the registry; type checkers see its base, which declares every method.
if TYPE_CHECKING:
    ProjectSettings = _ProjectSettings
else:
    ProjectSettings = create_model(
        "ProjectSettings",
        __base__=_ProjectSettings,
        __doc__=_ProjectSettings.__doc__,
        **{name: (dict[AccountName, spec.account], {}) for name, spec in PLATFORMS.items()},
    )


class BucketSettings(BaseModel):
    """The S3-compatible bucket (Cloudflare R2) that serves videos to Instagram and keeps the backups."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    endpoint: str
    access_key_id: str
    secret_access_key: SecretStr
    name: str


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        toml_file=CONFIG_FILE,
        env_prefix="POSTILLON_",
        env_nested_delimiter="__",
        extra="ignore",
        frozen=True,
    )

    # Holds the database and the videos waiting for their platforms.
    data_dir: Path = Path("data")
    poll_seconds: PositiveInt = 60
    # YouTube accepts far larger files, but a short vertical video stays well under it.
    max_video_bytes: PositiveInt = 1024**3
    bucket: BucketSettings
    projects: dict[ProjectName, ProjectSettings] = Field(min_length=1)

    @property
    def database(self) -> Path:
        return self.data_dir / "postillon.db"

    @property
    def videos_dir(self) -> Path:
        return self.data_dir / "videos"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # The environment overrides the file, so that secrets never have to be written in it.
        return init_settings, env_settings, TomlConfigSettingsSource(settings_cls)
