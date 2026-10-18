import os
import stat

import pytest

from postillon import cli, environment

CONFIG = """
[projects.my-project.youtube.my-youtube]
handle = "@mychannel"
refresh_token_env = "MY_YOUTUBE_REFRESH_TOKEN"
"""


@pytest.fixture
def workdir(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MY_YOUTUBE_REFRESH_TOKEN", raising=False)
    (tmp_path / "postillon.toml").write_text(CONFIG)
    return tmp_path


def test_login_saves_the_secrets_to_dotenv(monkeypatch, workdir):
    calls = []

    def login(platform, account, settings):
        calls.append((platform, account, settings))
        return {"MY_YOUTUBE_REFRESH_TOKEN": "new-token"}

    monkeypatch.setattr(cli, "login", login)
    cli.main(["login", "my-project", "youtube", "my-youtube"])
    assert calls == [("youtube", "my-youtube", {"handle": "@mychannel", "refresh_token_env": "MY_YOUTUBE_REFRESH_TOKEN"})]
    assert (workdir / ".env").read_text() == "MY_YOUTUBE_REFRESH_TOKEN=new-token\n"


def test_login_of_an_undeclared_account_exits(workdir, capsys):
    with pytest.raises(SystemExit) as exit:
        cli.main(["login", "my-project", "youtube", "other"])
    assert exit.value.code == 2
    assert "my-project.youtube.other is not in postillon.toml" in capsys.readouterr().err


def test_saved_variable_is_private_and_replaced(workdir):
    environment.save("MY_YOUTUBE_REFRESH_TOKEN", "first")
    environment.save("MY_YOUTUBE_REFRESH_TOKEN", "second")
    env = workdir / ".env"
    assert env.read_text() == "MY_YOUTUBE_REFRESH_TOKEN=second\n"
    assert stat.S_IMODE(env.stat().st_mode) == 0o600
    assert os.environ["MY_YOUTUBE_REFRESH_TOKEN"] == "second"


def test_missing_variable_is_named(workdir):
    with pytest.raises(ValueError, match="MY_YOUTUBE_REFRESH_TOKEN"):
        environment.variable("MY_YOUTUBE_REFRESH_TOKEN")
