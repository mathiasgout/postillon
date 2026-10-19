import io
import json
import stat
from datetime import UTC, datetime, timedelta
from urllib.error import HTTPError

import pytest
from pydantic import ValidationError

from postillon.domain import PostState, Status
from postillon.platforms.base import Task
from postillon.platforms.instagram import InstagramAccount, InstagramPost
from postillon.platforms.instagram import client as instagram_client
from postillon.platforms.instagram.client import GraphError, InstagramPlatform

NO_STATE = PostState()
PUBLISH_AT = datetime(2026, 10, 19, 6, 0, tzinfo=UTC)
BEFORE = PUBLISH_AT - timedelta(hours=1)
SETTINGS = {"username": "mychannel", "access_token_env": "MY_INSTAGRAM_TOKEN"}
ACCOUNTS = {"my-instagram": InstagramAccount(**SETTINGS)}
USER_ID = "17841"


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
    monkeypatch.setattr(instagram_client, "_request", fake.request)
    monkeypatch.setattr(instagram_client, "_refresh", fake.refresh)
    return fake


@pytest.fixture(autouse=True)
def secrets(monkeypatch):
    monkeypatch.setenv("MY_INSTAGRAM_TOKEN", "seed")


@pytest.fixture
def tokens(tmp_path):
    return tmp_path / "instagram-tokens.json"


@pytest.fixture
def step(api, tokens):
    platform = InstagramPlatform(ACCOUNTS, tokens)

    def step(state=NO_STATE, now=PUBLISH_AT, next_publish_at=None, **post):
        task = Task(
            post=InstagramPost(**{"account": "my-instagram", **post}),
            publish_at=PUBLISH_AT,
            state=state,
            now=now,
            video=FakeVideo(),
            checkpoint=lambda state: None,
            next_publish_at=next_publish_at,
        )
        return platform.step(task)

    return step


def in_container(container="c1"):
    return PostState(status=Status.IN_PROGRESS, extra={"container_id": container})


@pytest.mark.parametrize(
    ("settings", "message"),
    [
        ({"username": "mychannel"}, "Field required"),
        ({**SETTINGS, "token": "x"}, "Extra inputs"),
        ({**SETTINGS, "username": ""}, "pattern"),
    ],
)
def test_invalid_account_settings(settings, message):
    with pytest.raises(ValidationError, match=message):
        InstagramAccount(**settings)


def test_missing_secret_refuses_the_start(monkeypatch, tokens):
    monkeypatch.delenv("MY_INSTAGRAM_TOKEN")
    with pytest.raises(ValueError, match="MY_INSTAGRAM_TOKEN"):
        InstagramPlatform(ACCOUNTS, tokens)


def test_post_waits_for_its_publication_time(step, api):
    state = PostState()
    assert step(state=state, now=BEFORE) is state
    assert api.created == []


def test_publication_time_creates_the_container(step, api):
    new = step(caption="Pasta #cooking", share_to_feed=False, thumb_offset=1500)
    assert api.created == [
        {
            "media_type": "REELS",
            "video_url": "https://signed.example/video.mp4?expires=3600",
            "caption": "Pasta #cooking",
            "share_to_feed": "false",
            "thumb_offset": "1500",
        }
    ]
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
    new = step(
        state=in_container(), now=PUBLISH_AT + timedelta(hours=12), next_publish_at=PUBLISH_AT + timedelta(hours=12)
    )
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
    assert ("POST", f"{USER_ID}/media_publish", "seed") in api.calls


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


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (400, {"code": 4, "message": "Application request limit reached"}),
        (400, {"code": 9, "message": "Publishing limit reached"}),
        (400, {"code": 190, "message": "Invalid OAuth access token"}),
        (400, {"code": 100, "is_transient": True}),
        (500, {}),
    ],
)
def test_transient_errors_are_raised(step, api, status, error):
    api.refusal = GraphError(status, error)
    with pytest.raises(GraphError):
        step()


@pytest.fixture
def platform(api, tokens):
    return InstagramPlatform(ACCOUNTS, tokens)


def test_first_renewal_renews_the_token_of_the_environment(platform, api, tokens):
    platform.renew_credentials(BEFORE)
    assert api.renewed == ["seed"]
    assert json.loads(tokens.read_text())["MY_INSTAGRAM_TOKEN"]["token"] == "seed+"
    assert stat.S_IMODE(tokens.stat().st_mode) == 0o600


def test_steps_use_the_renewed_token_without_renewing(step, platform, api):
    step(now=BEFORE)
    assert api.renewed == []
    assert api.calls[-1][2] == "seed"
    platform.renew_credentials(BEFORE)
    step(now=PUBLISH_AT)
    assert api.calls[-1] == ("POST", f"{USER_ID}/media", "seed+")


def test_token_is_renewed_again_after_a_week(platform, api):
    platform.renew_credentials(BEFORE)
    platform.renew_credentials(BEFORE + timedelta(days=6))
    assert api.renewed == ["seed"]
    platform.renew_credentials(BEFORE + timedelta(days=7))
    assert api.renewed == ["seed", "seed+"]


def test_renewed_token_survives_a_restart(api, tokens):
    instagram_client.Tokens(tokens).save("MY_INSTAGRAM_TOKEN", "seed", "seed+", BEFORE)
    assert instagram_client.Tokens(tokens).current("MY_INSTAGRAM_TOKEN", "seed") == ("seed+", BEFORE)


def test_token_placed_in_the_environment_replaces_the_renewed_one(platform, api, monkeypatch):
    platform.renew_credentials(BEFORE)
    monkeypatch.setenv("MY_INSTAGRAM_TOKEN", "new-seed")
    platform.renew_credentials(BEFORE + timedelta(days=1))
    assert api.renewed == ["seed", "new-seed"]


def test_failed_renewal_keeps_the_token_and_waits_a_week(platform, api, caplog):
    api.renewal_refusal = GraphError(400, {"code": 190, "message": "token too recent"})
    platform.renew_credentials(BEFORE)
    assert "token not renewed" in caplog.text
    api.renewal_refusal = None
    platform.renew_credentials(BEFORE + timedelta(days=1))
    assert api.renewed == []
    platform.renew_credentials(BEFORE + timedelta(days=7))
    assert api.renewed == ["seed"]


def test_graph_error_is_read_from_the_response(monkeypatch):
    body = json.dumps({"error": {"message": "Invalid parameter", "code": 100}}).encode()

    def refuse(request, timeout):
        assert request.get_header("Authorization") == "Bearer token"
        raise HTTPError(request.full_url, 400, "Bad Request", {}, io.BytesIO(body))

    monkeypatch.setattr(instagram_client, "urlopen", refuse)
    with pytest.raises(GraphError) as error:
        instagram_client._request("GET", "me", {"fields": "username"}, "token")
    assert (error.value.status, error.value.code, error.value.retryable) == (400, 100, False)
