import io
import json
import stat
from datetime import UTC, datetime, timedelta
from urllib.error import HTTPError

import pytest

from postillon import Entry
from postillon.adapter import Task
from postillon.platforms.instagram import Instagram
from postillon.platforms.instagram import adapter as instagram_adapter
from postillon.platforms.instagram.adapter import Adapter, GraphError
from postillon.platforms.youtube import YouTube
from postillon.state import PostState, Status

PUBLISH_AT = datetime(2026, 10, 19, 6, 0, tzinfo=UTC)
BEFORE = PUBLISH_AT - timedelta(hours=1)
ACCOUNTS = {"my-instagram": {"username": "mychannel", "access_token_env": "MY_INSTAGRAM_TOKEN"}}
USER_ID = "17841"


def instagram(**fields):
    return Instagram(**{"account": "my-instagram", **fields})


def test_post_defaults_are_written_to_the_manifest():
    assert instagram().to_dict() == {"account": "my-instagram", "caption": "", "share_to_feed": True, "thumb_offset": 0}


def test_entry_with_both_platforms_round_trips():
    entry = Entry(
        id="pasta-in-ten-minutes", publish_at=PUBLISH_AT,
        posts=[YouTube(account="my-youtube", title="Pasta"), instagram(caption="Pasta #cooking", thumb_offset=1500)],
    )
    assert Entry.from_manifest(entry.id, entry.to_manifest()) == entry


@pytest.mark.parametrize(("fields", "message"), [
    ({"caption": "x" * 2201}, "2201 characters"),
    ({"caption": " ".join(f"#tag{i}" for i in range(31))}, "31 hashtags"),
    ({"caption": " ".join(f"@user{i}" for i in range(21))}, "21 mentions"),
    ({"caption": None}, "caption must be a string"),
    ({"share_to_feed": "yes"}, "boolean"),
    ({"thumb_offset": -1}, "thumb_offset"),
    ({"thumb_offset": True}, "thumb_offset"),
])
def test_invalid_instagram_posts(fields, message):
    with pytest.raises(ValueError, match=message):
        instagram(**fields).validate()


def test_instagram_limits_are_inclusive():
    instagram(caption="x" * 2200).validate()
    instagram(caption=" ".join(f"#tag{i}" for i in range(30)) + " " + " ".join(f"@user{i}" for i in range(20))).validate()


def test_a_hash_inside_a_word_is_no_hashtag():
    instagram(caption="C#" * 40).validate()


class FakeInstagram:
    """The Graph API of one account, with its containers by identifier."""

    def __init__(self):
        self.username = "mychannel"
        self.containers = {}
        self.created = []
        self.calls = []
        self.renewed = []
        self.refusal = None
        self.renewal_refusal = None

    def request(self, method, path, params, token):
        self.calls.append((method, path, token))
        if self.refusal:
            raise self.refusal
        if path == "me":
            return {"user_id": USER_ID, "username": self.username}
        if path == f"{USER_ID}/media":
            self.created.append(params)
            container = f"c{len(self.created)}"
            self.containers[container] = "IN_PROGRESS"
            return {"id": container}
        if path == f"{USER_ID}/media_publish":
            self.containers[params["creation_id"]] = "PUBLISHED"
            return {"id": "m1"}
        return {"status_code": self.containers[path], "status": "Error: unsupported codec"}

    def refresh(self, token):
        if self.renewal_refusal:
            raise self.renewal_refusal
        self.renewed.append(token)
        return f"{token}+"


class FakeVideo:
    def url(self, expires_seconds):
        return f"https://signed.example/video.mp4?expires={expires_seconds}"


@pytest.fixture
def api(monkeypatch):
    fake = FakeInstagram()
    monkeypatch.setattr(instagram_adapter, "_request", fake.request)
    monkeypatch.setattr(instagram_adapter, "_refresh", fake.refresh)
    return fake


@pytest.fixture(autouse=True)
def secrets(monkeypatch):
    monkeypatch.setenv("MY_INSTAGRAM_TOKEN", "seed")


@pytest.fixture
def tokens(tmp_path):
    return tmp_path / "instagram-tokens.json"


@pytest.fixture
def step(api, tokens):
    adapter = Adapter(ACCOUNTS, tokens=tokens)

    def step(state=PostState(), now=PUBLISH_AT, next_publish_at=None, **post):
        post = instagram(**post)
        entry = Entry(id="pasta-in-ten-minutes", publish_at=PUBLISH_AT, posts=[post])
        task = Task(
            entry=entry, post=post, state=state, now=now, video=FakeVideo(), checkpoint=lambda state: None,
            next_publish_at=next_publish_at,
        )
        return adapter.step(task)

    return step


def in_container(container="c1"):
    return PostState(status=Status.IN_PROGRESS, extra={"container_id": container})


@pytest.mark.parametrize(("settings", "message"), [
    ({"username": "mychannel"}, "missing settings"),
    ({**ACCOUNTS["my-instagram"], "token": "x"}, "unknown settings"),
    ({**ACCOUNTS["my-instagram"], "username": ""}, "non-empty string"),
])
def test_invalid_account_settings(settings, message, tokens):
    with pytest.raises(ValueError, match=message):
        Adapter({"my-instagram": settings}, tokens=tokens)


def test_missing_secret_refuses_the_start(monkeypatch, tokens):
    monkeypatch.delenv("MY_INSTAGRAM_TOKEN")
    with pytest.raises(ValueError, match="MY_INSTAGRAM_TOKEN"):
        Adapter(ACCOUNTS, tokens=tokens)


def test_post_waits_for_its_publication_time(step, api):
    state = PostState()
    assert step(state=state, now=BEFORE) is state
    assert api.created == []


def test_publication_time_creates_the_container(step, api):
    new = step(caption="Pasta #cooking", share_to_feed=False, thumb_offset=1500)
    assert api.created == [{
        "media_type": "REELS",
        "video_url": "https://signed.example/video.mp4?expires=3600",
        "caption": "Pasta #cooking",
        "share_to_feed": "false",
        "thumb_offset": "1500",
    }]
    assert (new.status, new.extra) == (Status.IN_PROGRESS, {"container_id": "c1"})


def test_late_post_is_published_late(step, api):
    step(now=PUBLISH_AT + timedelta(days=2))
    assert len(api.created) == 1


def test_late_post_is_published_before_the_next_one_is_due(step, api):
    step(now=PUBLISH_AT + timedelta(hours=11), next_publish_at=PUBLISH_AT + timedelta(hours=12))
    assert len(api.created) == 1


def test_late_post_is_rejected_once_the_next_one_is_due(step, api):
    new = step(now=PUBLISH_AT + timedelta(hours=12), next_publish_at=PUBLISH_AT + timedelta(hours=12))
    assert api.created == []
    assert new.status == Status.REJECTED
    assert new.error == "missed: the account's next Reel was due at 2026-10-19T18:00:00Z"


def test_container_created_in_time_is_published_after_the_next_one_is_due(step, api):
    api.containers["c1"] = "FINISHED"
    new = step(state=in_container(), now=PUBLISH_AT + timedelta(hours=12), next_publish_at=PUBLISH_AT + timedelta(hours=12))
    assert new.status == Status.PUBLISHED


def test_container_in_progress_waits(step, api):
    step()
    state = in_container()
    assert step(state=state) is state


def test_finished_container_is_published(step, api):
    step()
    api.containers["c1"] = "FINISHED"
    new = step(state=in_container())
    assert (new.status, new.remote_id, new.extra) == (Status.PUBLISHED, "m1", {})
    assert ("POST", f"{USER_ID}/media_publish", "seed+") in api.calls


def test_container_published_on_a_lost_pass_confirms_the_post(step, api):
    api.containers["c1"] = "PUBLISHED"
    new = step(state=in_container())
    assert (new.status, new.remote_id, new.extra) == (Status.PUBLISHED, None, {})


def test_expired_container_fails_the_post(step, api):
    api.containers["c1"] = "EXPIRED"
    new = step(state=in_container())
    assert (new.status, new.extra) == (Status.FAILED, {})
    assert "expired" in new.error


def test_unprocessable_video_rejects_the_post(step, api):
    api.containers["c1"] = "ERROR"
    new = step(state=in_container())
    assert (new.status, new.extra) == (Status.REJECTED, {})
    assert new.error == "Instagram could not process the video (ERROR: Error: unsupported codec)"


def test_token_of_another_account_is_refused(step, api):
    api.username = "otherchannel"
    with pytest.raises(ValueError, match="authorizes otherchannel, not mychannel"):
        step()
    assert api.created == []


def test_refusal_rejects_the_post(step, api):
    api.refusal = GraphError(400, {"code": 100, "message": "Invalid parameter"})
    new = step(state=in_container())
    assert (new.status, new.extra) == (Status.REJECTED, {})
    assert new.error == "Instagram refused (400 code 100: Invalid parameter)"


@pytest.mark.parametrize(("status", "error"), [
    (400, {"code": 4, "message": "Application request limit reached"}),
    (400, {"code": 9, "message": "Publishing limit reached"}),
    (400, {"code": 190, "message": "Invalid OAuth access token"}),
    (400, {"code": 100, "is_transient": True}),
    (500, {}),
])
def test_transient_errors_are_raised(step, api, status, error):
    api.refusal = GraphError(status, error)
    with pytest.raises(GraphError):
        step()


def test_first_use_renews_the_token_from_dotenv(step, api, tokens):
    step(now=BEFORE)
    assert api.renewed == ["seed"]
    assert json.loads(tokens.read_text())["MY_INSTAGRAM_TOKEN"]["token"] == "seed+"
    assert stat.S_IMODE(tokens.stat().st_mode) == 0o600


def test_renewed_token_is_used_then_renewed_after_a_week(step, api):
    step(now=BEFORE)
    step(now=BEFORE + timedelta(days=6))
    assert api.renewed == ["seed"]
    assert api.calls[-1][2] == "seed+"
    step(now=BEFORE + timedelta(days=7))
    assert api.renewed == ["seed", "seed+"]


def test_renewed_token_survives_a_restart(api, tokens):
    instagram_adapter.Tokens(tokens).save("MY_INSTAGRAM_TOKEN", "seed", "seed+", BEFORE)
    assert instagram_adapter.Tokens(tokens).current("MY_INSTAGRAM_TOKEN", "seed") == ("seed+", BEFORE)


def test_token_placed_in_dotenv_replaces_the_renewed_one(step, api, monkeypatch):
    step(now=BEFORE)
    monkeypatch.setenv("MY_INSTAGRAM_TOKEN", "new-seed")
    step(now=BEFORE + timedelta(days=1))
    assert api.renewed == ["seed", "new-seed"]
    assert api.calls[-1][2] == "new-seed+"


def test_failed_renewal_keeps_the_token_and_waits_a_week(step, api, caplog):
    api.renewal_refusal = GraphError(400, {"code": 190, "message": "token too recent"})
    step(now=BEFORE)
    assert api.calls[-1][2] == "seed"
    assert "token not renewed" in caplog.text
    api.renewal_refusal = None
    step(now=BEFORE + timedelta(days=1))
    assert api.renewed == []


def test_graph_error_is_read_from_the_response(monkeypatch):
    body = json.dumps({"error": {"message": "Invalid parameter", "code": 100}}).encode()

    def refuse(request, timeout):
        assert request.get_header("Authorization") == "Bearer token"
        raise HTTPError(request.full_url, 400, "Bad Request", {}, io.BytesIO(body))

    monkeypatch.setattr(instagram_adapter, "urlopen", refuse)
    with pytest.raises(GraphError) as error:
        instagram_adapter._request("GET", "me", {"fields": "username"}, "token")
    assert (error.value.status, error.value.code, error.value.retryable) == (400, 100, False)
