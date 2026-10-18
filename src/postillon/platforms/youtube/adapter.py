"""The YouTube adapter: uploads each video as private with `publishAt`, confirms its
publication, and connects accounts (see docs/youtube.md).

Only module that talks to YouTube, through the YouTube Data API v3 of the `youtube` extra.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime
from typing import Any, Self

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from postillon import environment
from postillon.adapter import Task
from postillon.platforms.youtube.post import YouTube
from postillon.state import PostState, Status

CLIENT_ID = "POSTILLON_YOUTUBE_CLIENT_ID"
CLIENT_SECRET = "POSTILLON_YOUTUBE_CLIENT_SECRET"
TOKEN_URI = "https://oauth2.googleapis.com/token"
# The upload, then the reads: the authorized channel, its recent uploads and their status.
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]
# Recent uploads searched for a video whose upload was interrupted; 50 is the maximum of one
# playlistItems.list page.
RECENT_UPLOADS = 50
# Set on the state while an upload may have reached YouTube.
UPLOADING = "uploading"
# Refusals worth retrying on a later pass; any other 4xx refuses the post until its manifest changes.
RETRYABLE_STATUSES = {401, 408, 429}
RETRYABLE_REASONS = {"quotaExceeded", "rateLimitExceeded", "userRateLimitExceeded", "uploadLimitExceeded"}


@dataclasses.dataclass(frozen=True)
class Account:
    handle: str
    refresh_token_env: str
    client_id_env: str = CLIENT_ID
    client_secret_env: str = CLIENT_SECRET

    @classmethod
    def from_settings(cls, name: str, settings: dict[str, Any]) -> Self:
        """The account read from its configuration; raises ValueError on an unknown, missing or non-string setting."""
        fields = {f.name for f in dataclasses.fields(cls)}
        unknown = sorted(set(settings) - fields)
        if unknown:
            raise ValueError(f"youtube account {name}: unknown settings {unknown}")
        missing = sorted({"handle", "refresh_token_env"} - set(settings))
        if missing:
            raise ValueError(f"youtube account {name}: missing settings {missing}")
        for key, value in settings.items():
            if not isinstance(value, str) or not value:
                raise ValueError(f"youtube account {name}: {key} must be a non-empty string")
        if not settings["handle"].startswith("@"):
            raise ValueError(f"youtube account {name}: handle must start with @")
        return cls(**settings)

    def client_config(self) -> dict[str, Any]:
        return {"installed": {
            "client_id": environment.variable(self.client_id_env),
            "client_secret": environment.variable(self.client_secret_env),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": TOKEN_URI,
            "redirect_uris": ["http://localhost"],
        }}

    def credentials(self) -> Credentials:
        """Credentials that obtain their access token from the refresh token; raises ValueError if a secret is missing."""
        client = self.client_config()["installed"]
        return Credentials(
            None,
            refresh_token=environment.variable(self.refresh_token_env),
            token_uri=TOKEN_URI,
            client_id=client["client_id"],
            client_secret=client["client_secret"],
            scopes=SCOPES,
        )


class Adapter:
    def __init__(self, accounts: dict[str, dict[str, Any]]):
        self._accounts = {name: Account.from_settings(name, settings) for name, settings in accounts.items()}
        # Fails at start on a missing secret rather than on the first post.
        for account in self._accounts.values():
            account.credentials()
        self._clients: dict[str, Any] = {}

    def step(self, task: Task) -> PostState:
        try:
            return self._step(task)
        except HttpError as e:
            if _retryable(e):
                raise
            extra = {k: v for k, v in task.state.extra.items() if k != UPLOADING}
            return dataclasses.replace(task.state, status=Status.REJECTED, error=_reason(e), extra=extra)

    def _step(self, task: Task) -> PostState:
        youtube = self._client(task.post.account)
        if task.state.remote_id is not None:
            return _confirm(youtube, task.state)
        found = _find_upload(youtube, task.post, task.entry.publish_at) if task.state.extra.get(UPLOADING) else None
        if found is not None:
            return _settled(task.state, found["id"], found["status"])
        path = task.video.file()
        task.checkpoint(dataclasses.replace(task.state, status=Status.IN_PROGRESS, extra={UPLOADING: True}))
        status = _status(task.post, task.entry.publish_at, task.now)
        return _settled(task.state, _upload(youtube, task.post, path, status), status)

    def _client(self, account: str):
        """The API client of the account, built once and checked against its handle; raises ValueError
        when the token belongs to another channel."""
        if account not in self._clients:
            settings = self._accounts[account]
            youtube = _build(settings.credentials())
            _check_handle(youtube, settings.handle)
            self._clients[account] = youtube
        return self._clients[account]


def login(name: str, settings: dict[str, Any]) -> dict[str, str]:
    """Authorizes the account's channel in a browser and returns its refresh token by variable name;
    raises ValueError if the authorized channel does not carry the configured handle."""
    account = Account.from_settings(name, settings)
    # Consent asked again guarantees a refresh token, which Google only issues on an account's first consent.
    creds = InstalledAppFlow.from_client_config(account.client_config(), SCOPES).run_local_server(
        port=0, prompt="consent",
    )
    _check_handle(_build(creds), account.handle)
    return {account.refresh_token_env: creds.refresh_token}


def _status(post: YouTube, publish_at: datetime, now: datetime) -> dict[str, Any]:
    """The status to upload with: private until `publish_at`, public once it has passed."""
    status = {
        "selfDeclaredMadeForKids": post.made_for_kids,
        "containsSyntheticMedia": post.contains_synthetic_media,
    }
    if publish_at <= now:
        return {"privacyStatus": "public", **status}
    # YouTube accepts `publishAt` on a private video only, and makes it public at that time.
    return {"privacyStatus": "private", "publishAt": _rfc3339(publish_at), **status}


def _upload(youtube, post: YouTube, path, status: dict[str, Any]) -> str:
    snippet = {"title": post.title, "description": post.description, "categoryId": post.category_id}
    media = MediaFileUpload(str(path), mimetype="video/mp4", chunksize=-1, resumable=True)
    request = youtube.videos().insert(
        part="snippet,status", body={"snippet": snippet, "status": status}, media_body=media,
    )
    response = None
    while response is None:
        _, response = request.next_chunk()
    return response["id"]


def _confirm(youtube, state: PostState) -> PostState:
    """The post once `publish_at` is reached: `published` when the video is public, unchanged while
    YouTube has yet to publish it, `rejected` when it is no longer on the channel or no longer scheduled."""
    items = youtube.videos().list(part="status", id=state.remote_id).execute().get("items", [])
    if not items:
        return dataclasses.replace(
            state, status=Status.REJECTED, error=f"video {state.remote_id} is no longer on the channel",
        )
    status = items[0]["status"]
    if status["privacyStatus"] == "public":
        return _settled(state, state.remote_id, status)
    if status.get("publishAt"):
        return state
    return dataclasses.replace(
        state, status=Status.REJECTED, error=f"video {state.remote_id} is no longer scheduled on YouTube",
    )


def _settled(state: PostState, video_id: str, status: dict[str, Any]) -> PostState:
    published = status["privacyStatus"] == "public"
    return dataclasses.replace(
        state, status=Status.PUBLISHED if published else Status.SCHEDULED, remote_id=video_id, error=None, extra={},
    )


def _find_upload(youtube, post: YouTube, publish_at: datetime) -> dict[str, Any] | None:
    """The recent upload of the channel that carries the post's title and was scheduled at `publish_at`,
    or published after it when uploaded late; none if the upload did not reach YouTube."""
    uploads = _own_channel(youtube, "contentDetails")["contentDetails"]["relatedPlaylists"]["uploads"]
    items = youtube.playlistItems().list(
        part="contentDetails", playlistId=uploads, maxResults=RECENT_UPLOADS,
    ).execute().get("items", [])
    ids = [item["contentDetails"]["videoId"] for item in items]
    if not ids:
        return None
    videos = youtube.videos().list(part="snippet,status", id=",".join(ids)).execute().get("items", [])
    for video in videos:
        if video["snippet"]["title"] != post.title:
            continue
        scheduled = video["status"].get("publishAt")
        if scheduled and _parse(scheduled) == publish_at:
            return video
        if not scheduled and _parse(video["snippet"]["publishedAt"]) >= publish_at:
            return video
    return None


def _check_handle(youtube, handle: str) -> None:
    found = _own_channel(youtube, "snippet")["snippet"].get("customUrl", "").lstrip("@")
    if found.lower() != handle.lstrip("@").lower():
        raise ValueError(f"the token authorizes @{found}, not {handle}: log in again with the right channel")


def _own_channel(youtube, part: str) -> dict[str, Any]:
    items = youtube.channels().list(part=part, mine=True).execute().get("items", [])
    if not items:
        raise ValueError("the authorized Google account has no YouTube channel")
    return items[0]


def _build(creds: Credentials):
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def _retryable(error: HttpError) -> bool:
    status = error.resp.status
    if status >= 500 or status in RETRYABLE_STATUSES:
        return True
    return bool(RETRYABLE_REASONS & set(_reasons(error)))


def _reason(error: HttpError) -> str:
    return f"YouTube refused ({error.resp.status} {', '.join(_reasons(error)) or error.reason})"


def _reasons(error: HttpError) -> list[str]:
    """The reasons of the `errors` list of the response body, where YouTube names a refusal."""
    try:
        errors = json.loads(error.content)["error"]["errors"]
        return [e["reason"] for e in errors if isinstance(e, dict) and e.get("reason")]
    except (ValueError, KeyError, TypeError):
        return []


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _rfc3339(when: datetime) -> str:
    return when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
