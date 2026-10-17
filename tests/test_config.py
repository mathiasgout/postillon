import pytest

from postillon.config import load_config

VALID = """
poll_seconds = 30

[projects.my-project.youtube.my-youtube]
handle = "@mychannel"

[projects.other-project.youtube.main]
"""


def write(tmp_path, text):
    path = tmp_path / "postillon.toml"
    path.write_text(text)
    return path


def test_valid_configuration(tmp_path):
    config = load_config(write(tmp_path, VALID))
    assert config.poll_seconds == 30
    assert config.projects == {
        "my-project": {"youtube": {"my-youtube": {"handle": "@mychannel"}}},
        "other-project": {"youtube": {"main": {}}},
    }


def test_poll_seconds_defaults_to_a_minute(tmp_path):
    config = load_config(write(tmp_path, "[projects.my-project.youtube.main]\n"))
    assert config.poll_seconds == 60


@pytest.mark.parametrize(("text", "message"), [
    ("[projects.my-project.youtube.main]\n[other]\n", "unknown configuration keys"),
    ("poll_seconds = 0\n[projects.p.youtube.main]\n", "poll_seconds"),
    ("poll_seconds = true\n[projects.p.youtube.main]\n", "poll_seconds"),
    ("poll_seconds = 60\n", "no project"),
    ("[projects.My_Project.youtube.main]\n", "project 'My_Project'"),
    ("[projects.p.tiktok.main]\n", "unknown platform 'tiktok'"),
    ("[projects.p.youtube.'My Account']\n", "account 'My Account'"),
    ("[projects]\np = 1\n", "p must be a table"),
    ("[projects.p]\nyoutube = 1\n", "p.youtube must be a table"),
    ("[projects.p.youtube]\nmain = 1\n", "p.youtube.main must be a table"),
    ("[projects.p", "not valid TOML"),
])
def test_invalid_configurations(tmp_path, text, message):
    with pytest.raises(ValueError, match=message):
        load_config(write(tmp_path, text))


def test_missing_configuration(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        load_config(tmp_path / "postillon.toml")
