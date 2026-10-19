from pathlib import Path

import pytest
from pydantic import ValidationError

from postillon.settings import Settings

TOML = """
poll_seconds = 30

[bucket]
endpoint = "https://r2.example"
access_key_id = "id"
name = "videos"

[projects.my-project.youtube.main]
handle = "@mychannel"
refresh_token_env = "MY_YOUTUBE_TOKEN"
"""


@pytest.fixture
def workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("POSTILLON_BUCKET__SECRET_ACCESS_KEY", "secret")
    return tmp_path


def test_settings_read_the_file_and_the_secrets_from_the_environment(workdir: Path):
    (workdir / "postillon.toml").write_text(TOML)
    settings = Settings()
    assert settings.poll_seconds == 30
    assert settings.bucket.secret_access_key.get_secret_value() == "secret"
    assert settings.projects["my-project"].accounts("youtube") == {"main"}
    assert settings.projects["my-project"].accounts("instagram") == set()
    assert settings.database == Path("data/postillon.db")


def test_environment_overrides_the_file(workdir: Path, monkeypatch: pytest.MonkeyPatch):
    (workdir / "postillon.toml").write_text(TOML)
    monkeypatch.setenv("POSTILLON_POLL_SECONDS", "5")
    assert Settings().poll_seconds == 5


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (("[projects.my-project.youtube.main]", "[projects.My_Project.youtube.main]"), "pattern"),
        (("[projects.my-project.youtube.main]", "[projects.my-project.tiktok.main]"), "Extra inputs"),
        (('handle = "@mychannel"', 'handle = "mychannel"'), "pattern"),
        (('refresh_token_env = "MY_YOUTUBE_TOKEN"', 'refresh_token = "x"'), "Field required"),
        (("poll_seconds = 30", "poll_seconds = 0"), "greater than 0"),
    ],
)
def test_invalid_settings(workdir: Path, change: tuple[str, str], message: str):
    (workdir / "postillon.toml").write_text(TOML.replace(*change))
    with pytest.raises(ValidationError, match=message):
        Settings()


def test_a_configuration_without_project_is_refused(workdir: Path):
    (workdir / "postillon.toml").write_text(TOML.split("[projects", maxsplit=1)[0])
    with pytest.raises(ValidationError, match="projects"):
        Settings()
