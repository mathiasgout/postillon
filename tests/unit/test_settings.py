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
    monkeypatch.setenv("POSTILLON_BUCKET__SECRET_ACCESS_KEY", "secret")
    return tmp_path


def load(workdir: Path, toml: str = TOML) -> Settings:
    (workdir / "postillon.toml").write_text(toml)
    return Settings.load(workdir / "postillon.toml")


def test_settings_read_the_file_and_the_secrets_from_the_environment(workdir: Path):
    settings = load(workdir)
    assert settings.poll_seconds == 30
    assert settings.bucket.secret_access_key.get_secret_value() == "secret"
    assert settings.projects["my-project"].accounts("youtube") == {"main"}
    assert settings.projects["my-project"].accounts("instagram") == set()
    assert settings.database == workdir / "data" / "postillon.db"


def test_environment_overrides_the_file(workdir: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("POSTILLON_POLL_SECONDS", "5")
    assert load(workdir).poll_seconds == 5


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (("[projects.my-project.youtube.main]", "[projects.My_Project.youtube.main]"), "pattern"),
        (("[projects.my-project.youtube.main]", "[projects.my-project.tiktok.main]"), "Extra inputs"),
        (('handle = "@mychannel"', 'handle = "mychannel"'), "pattern"),
        (('refresh_token_env = "MY_YOUTUBE_TOKEN"', 'refresh_token = "x"'), "Field required"),
        (("poll_seconds = 30", "poll_seconds = 0"), "greater than 0"),
        (("poll_seconds = 30", "poll_second = 30"), "Extra inputs"),
    ],
)
def test_invalid_settings(workdir: Path, change: tuple[str, str], message: str):
    with pytest.raises(ValidationError, match=message):
        load(workdir, TOML.replace(*change))


def test_a_configuration_without_project_is_refused(workdir: Path):
    with pytest.raises(ValidationError, match="projects"):
        load(workdir, TOML.split("[projects", maxsplit=1)[0])


def test_an_absolute_data_dir_is_kept(workdir: Path):
    assert load(workdir, f'data_dir = "/srv/postillon"\n{TOML}').data_dir == Path("/srv/postillon")
