import pytest

from postillon import environment


def test_dotenv_completes_the_environment(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    # Set then removed, so that the variable `load` adds is removed after the test.
    monkeypatch.setenv("MY_YOUTUBE_REFRESH_TOKEN", "")
    monkeypatch.delenv("MY_YOUTUBE_REFRESH_TOKEN")
    monkeypatch.setenv("POSTILLON_BUCKET", "from-process")
    (tmp_path / ".env").write_text("MY_YOUTUBE_REFRESH_TOKEN=from-file\nPOSTILLON_BUCKET=from-file\n")
    environment.load()
    assert environment.variable("MY_YOUTUBE_REFRESH_TOKEN") == "from-file"
    assert environment.variable("POSTILLON_BUCKET") == "from-process"


def test_missing_variable_is_named(monkeypatch):
    monkeypatch.delenv("MY_YOUTUBE_REFRESH_TOKEN", raising=False)
    with pytest.raises(ValueError, match="MY_YOUTUBE_REFRESH_TOKEN"):
        environment.variable("MY_YOUTUBE_REFRESH_TOKEN")
