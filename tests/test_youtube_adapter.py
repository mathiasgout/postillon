import dataclasses
import json
from datetime import UTC, datetime, timedelta

import pytest
from googleapiclient.errors import HttpError
from httplib2 import Response

from postillon import Entry
from postillon.adapter import Task
from postillon.platforms.youtube import YouTube
from postillon.platforms.youtube import adapter as youtube_adapter
from postillon.platforms.youtube.adapter import Adapter
from postillon.state import PostState, Status

PUBLISH_AT = datetime(2026, 10, 19, 6, 0, tzinfo=UTC)
BEFORE = PUBLISH_AT - timedelta(days=1)
ACCOUNTS = {"my-youtube": {"handle": "@mychannel", "refresh_token_env": "MY_YOUTUBE_REFRESH_TOKEN"}}


class Request:
    def __init__(self, call):
        self._call = call

    def execute(self):
        return self._call()

    def next_chunk(self):
        return None, self._call()


class Collection:
    """One collection of the API client, whose methods return requests run on `execute`."""

    def __init__(self, log, collection, **methods):
        self._log = log
        self._collection = collection
        self._methods = methods

    def __getattr__(self, name):
        def method(**params):
            self._log.append(f"{self._collection}.{name}")
            return Request(lambda: self._methods[name](**params))
        return method


class FakeYouTube:
    """A channel with its uploads, most recent first."""

    def __init__(self, handle="mychannel"):
        self.handle = handle
        self.videos_by_id = {}
        self.uploads = []
        self.inserted = []
        self.calls = []
        self.refusal = None

    def add_video(self, video_id, title, status, published_at="2026-10-18T06:00:00Z"):
        self.videos_by_id[video_id] = {
            "id": video_id, "snippet": {"title": title, "publishedAt": published_at}, "status": status,
        }
        self.uploads.insert(0, video_id)

    def channels(self):
        return Collection(self.calls, "channels", list=self._channel)

    def playlistItems(self):
        return Collection(self.calls, "playlistItems", list=self._playlist)

    def videos(self):
        return Collection(self.calls, "videos", list=self._list, insert=self._insert)

    def _channel(self, part, mine):
        return {"items": [{
            "id": "UC1",
            "snippet": {"customUrl": f"@{self.handle}"},
            "contentDetails": {"relatedPlaylists": {"uploads": "UU1"}},
        }]}

    def _playlist(self, part, playlistId, maxResults):
        return {"items": [{"contentDetails": {"videoId": v}} for v in self.uploads[:maxResults]]}

    def _list(self, part, id):
        return {"items": [self.videos_by_id[v] for v in id.split(",") if v in self.videos_by_id]}

    def _insert(self, part, body, media_body):
        if self.refusal:
            raise self.refusal
        self.inserted.append(body)
        video_id = f"new{len(self.inserted)}"
        self.add_video(video_id, body["snippet"]["title"], body["status"])
        return {"id": video_id}


class FakeVideo:
    def __init__(self, path):
        self.path = path

    def file(self):
        return self.path


@pytest.fixture
def youtube(monkeypatch):
    client = FakeYouTube()
    monkeypatch.setattr(youtube_adapter, "_build", lambda creds: client)
    return client


@pytest.fixture(autouse=True)
def secrets(monkeypatch):
    monkeypatch.setenv("POSTILLON_YOUTUBE_CLIENT_ID", "client-id")
    monkeypatch.setenv("POSTILLON_YOUTUBE_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("MY_YOUTUBE_REFRESH_TOKEN", "refresh-token")


@pytest.fixture
def step(youtube, tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    adapter = Adapter(ACCOUNTS)
    checkpoints = []

    def step(state=PostState(), now=BEFORE, **post):
        post = YouTube(**{"account": "my-youtube", "title": "Pasta in ten minutes", **post})
        entry = Entry(id="pasta-in-ten-minutes", publish_at=PUBLISH_AT, posts=[post])
        task = Task(
            entry=entry, post=post, state=state, now=now, video=FakeVideo(video), checkpoint=checkpoints.append,
        )
        return adapter.step(task)

    step.checkpoints = checkpoints
    return step


def http_error(status, reason):
    content = json.dumps({"error": {"code": status, "message": reason, "errors": [{"reason": reason}]}})
    return HttpError(Response({"status": status}), content.encode())


@pytest.mark.parametrize(("settings", "message"), [
    ({"handle": "@mychannel"}, "missing settings"),
    ({**ACCOUNTS["my-youtube"], "token": "x"}, "unknown settings"),
    ({**ACCOUNTS["my-youtube"], "handle": "mychannel"}, "must start with @"),
    ({**ACCOUNTS["my-youtube"], "handle": ""}, "non-empty string"),
])
def test_invalid_account_settings(settings, message):
    with pytest.raises(ValueError, match=message):
        Adapter({"my-youtube": settings})


def test_missing_secret_refuses_the_start(monkeypatch):
    monkeypatch.delenv("MY_YOUTUBE_REFRESH_TOKEN")
    with pytest.raises(ValueError, match="MY_YOUTUBE_REFRESH_TOKEN"):
        Adapter(ACCOUNTS)


def test_account_may_name_its_own_client(monkeypatch):
    monkeypatch.setenv("OTHER_CLIENT_ID", "other-id")
    settings = {**ACCOUNTS["my-youtube"], "client_id_env": "OTHER_CLIENT_ID"}
    creds = youtube_adapter.Account.from_settings("my-youtube", settings).credentials()
    assert creds.client_id == "other-id"


def test_upload_schedules_the_video(step, youtube):
    new = step(description="A quick weeknight recipe.", category_id="26")
    assert youtube.inserted == [{
        "snippet": {"title": "Pasta in ten minutes", "description": "A quick weeknight recipe.", "categoryId": "26"},
        "status": {
            "privacyStatus": "private",
            "publishAt": "2026-10-19T06:00:00Z",
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": False,
        },
    }]
    assert (new.status, new.remote_id, new.extra) == (Status.SCHEDULED, "new1", {})
    assert [(c.status, c.extra) for c in step.checkpoints] == [(Status.IN_PROGRESS, {"uploading": True})]


def test_upload_after_publish_at_publishes_at_once(step, youtube):
    new = step(now=PUBLISH_AT + timedelta(minutes=5))
    assert youtube.inserted[0]["status"]["privacyStatus"] == "public"
    assert "publishAt" not in youtube.inserted[0]["status"]
    assert new.status == Status.PUBLISHED


def test_token_of_another_channel_is_refused(step, youtube):
    youtube.handle = "otherchannel"
    with pytest.raises(ValueError, match="authorizes @otherchannel, not @mychannel"):
        step()
    assert youtube.inserted == []


def test_pending_post_uploads_without_searching(step, youtube):
    step()
    assert youtube.calls == ["channels.list", "videos.insert"]


def test_interrupted_upload_found_on_the_channel(step, youtube):
    youtube.add_video("vid1", "Pasta in ten minutes", {"privacyStatus": "private", "publishAt": "2026-10-19T06:00:00.000Z"})
    new = step(state=PostState(status=Status.IN_PROGRESS, extra={"uploading": True}))
    assert youtube.inserted == []
    assert (new.status, new.remote_id, new.extra) == (Status.SCHEDULED, "vid1", {})


def test_interrupted_late_upload_found_on_the_channel(step, youtube):
    youtube.add_video("vid1", "Pasta in ten minutes", {"privacyStatus": "public"}, published_at="2026-10-19T06:03:00Z")
    new = step(state=PostState(status=Status.FAILED, extra={"uploading": True}), now=PUBLISH_AT + timedelta(minutes=5))
    assert youtube.inserted == []
    assert (new.status, new.remote_id) == (Status.PUBLISHED, "vid1")


@pytest.mark.parametrize(("title", "status", "published_at"), [
    ("Pasta in nine minutes", {"privacyStatus": "private", "publishAt": "2026-10-19T06:00:00Z"}, "2026-10-18T06:00:00Z"),
    ("Pasta in ten minutes", {"privacyStatus": "private", "publishAt": "2026-10-20T06:00:00Z"}, "2026-10-18T06:00:00Z"),
    ("Pasta in ten minutes", {"privacyStatus": "public"}, "2026-10-01T06:00:00Z"),
])
def test_interrupted_upload_not_found_is_uploaded_again(step, youtube, title, status, published_at):
    youtube.add_video("vid1", title, status, published_at=published_at)
    new = step(state=PostState(status=Status.IN_PROGRESS, extra={"uploading": True}))
    assert len(youtube.inserted) == 1
    assert new.remote_id == "new1"


def test_public_video_confirms_the_publication(step, youtube):
    youtube.add_video("vid1", "Pasta in ten minutes", {"privacyStatus": "public"})
    new = step(state=PostState(status=Status.SCHEDULED, remote_id="vid1"), now=PUBLISH_AT)
    assert (new.status, new.remote_id) == (Status.PUBLISHED, "vid1")


def test_video_still_scheduled_waits(step, youtube):
    youtube.add_video("vid1", "Pasta in ten minutes", {"privacyStatus": "private", "publishAt": "2026-10-19T06:00:00Z"})
    state = PostState(status=Status.SCHEDULED, remote_id="vid1")
    assert step(state=state, now=PUBLISH_AT) == state


@pytest.mark.parametrize(("videos", "message"), [
    ({}, "no longer on the channel"),
    ({"vid1": {"privacyStatus": "private"}}, "no longer scheduled"),
])
def test_video_gone_or_unscheduled_rejects_the_post(step, youtube, videos, message):
    for video_id, status in videos.items():
        youtube.add_video(video_id, "Pasta in ten minutes", status)
    new = step(state=PostState(status=Status.SCHEDULED, remote_id="vid1"), now=PUBLISH_AT)
    assert new.status == Status.REJECTED
    assert message in new.error


def test_refusal_rejects_the_post(step, youtube):
    youtube.refusal = http_error(400, "invalidCategoryId")
    new = step(category_id="999")
    assert new.status == Status.REJECTED
    assert new.error == "YouTube refused (400 invalidCategoryId)"
    assert new.extra == {}


@pytest.mark.parametrize(("status", "reason"), [(403, "quotaExceeded"), (429, "rateLimitExceeded"), (503, "backendError")])
def test_transient_errors_are_raised(step, youtube, status, reason):
    youtube.refusal = http_error(status, reason)
    with pytest.raises(HttpError):
        step()


class FakeFlow:
    def run_local_server(self, port, prompt):
        assert prompt == "consent"
        return dataclasses.make_dataclass("Creds", ["refresh_token"])("new-token")


def test_login_returns_the_refresh_token(monkeypatch, youtube):
    monkeypatch.setattr(youtube_adapter.InstalledAppFlow, "from_client_config", lambda config, scopes: FakeFlow())
    assert youtube_adapter.login("my-youtube", ACCOUNTS["my-youtube"]) == {"MY_YOUTUBE_REFRESH_TOKEN": "new-token"}


def test_login_refuses_another_channel(monkeypatch, youtube):
    monkeypatch.setattr(youtube_adapter.InstalledAppFlow, "from_client_config", lambda config, scopes: FakeFlow())
    youtube.handle = "otherchannel"
    with pytest.raises(ValueError, match="otherchannel"):
        youtube_adapter.login("my-youtube", ACCOUNTS["my-youtube"])
