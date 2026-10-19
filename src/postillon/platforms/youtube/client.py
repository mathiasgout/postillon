"""The YouTube platform: uploads each video as private with `publishAt` and confirms its
publication (see docs/youtube.md).

Only module that talks to YouTube, through the YouTube Data API v3 of the `youtube` extra.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from postillon.domain import PostState, Status
from postillon.platforms.base import Task, read_secret
from postillon.platforms.youtube.post import YouTubePost
from postillon.platforms.youtube.settings import YouTubeAccount

TOKEN_URI = "https://oauth2.googleapis.com/token"
# The upload, then the reads: the authorized channel, its recent uploads and their status.
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]
# Recent uploads searched for a video whose upload was interrupted; 50 is the maximum of one
# playlistItems.list page.
RECENT_UPLOADS = 50
# Kept in the state while an upload may have reached YouTube.
UPLOADING = "uploading"
# Refusals worth retrying on a later pass; any other 4xx rejects the post until it is submitted again.
RETRYABLE_STATUSES = {401, 408, 429}
RETRYABLE_REASONS = {"quotaExceeded", "rateLimitExceeded", "userRateLimitExceeded", "uploadLimitExceeded"}

Client = Any  # The discovery client of googleapiclient, untyped.


class YouTubePlatform:
    def __init__(self, accounts: Mapping[str, YouTubeAccount]):
        self._accounts = dict(accounts)
        # Fails at start on a missing secret rather than on the first post.
        for account in self._accounts.values():
            _credentials(account)
        self._clients: dict[str, Client] = {}

    def step(self, task: Task) -> PostState:
        try:
            return self._step(task)
        except HttpError as e:
            if _retryable(e):
                raise
            extra = {k: v for k, v in task.state.extra.items() if k != UPLOADING}
            return dataclasses.replace(task.state, status=Status.REJECTED, error=_reason(e), extra=extra)

    def _step(self, task: Task) -> PostState:
        post = task.post
        assert isinstance(post, YouTubePost)
        youtube = self._client(post.account)
        if task.state.remote_id is not None:
            return _confirm(youtube, task.state)
        found = _find_upload(youtube, post, task.publish_at) if task.state.extra.get(UPLOADING) else None
        if found is not None:
            return _settled(task.state, found["id"], found["status"])
        path = task.video.file()
        task.checkpoint(dataclasses.replace(task.state, status=Status.IN_PROGRESS, extra={UPLOADING: True}))
        status = _status(post, task.publish_at, task.now)
        return _settled(task.state, _upload(youtube, post, path, status), status)

    def _client(self, account: str) -> Client:
        """The API client of the account, built once and checked against its handle; raises ValueError
        when the token belongs to another channel."""
        if account not in self._clients:
            settings = self._accounts[account]
            youtube = _build(_credentials(settings))
            _check_handle(youtube, settings.handle)
            self._clients[account] = youtube
        return self._clients[account]


def _credentials(account: YouTubeAccount) -> Credentials:
    """Credentials that obtain their access token from the refresh token; raises ValueError if a secret is missing."""
    return Credentials(  # type: ignore[no-untyped-call]
        None,
        refresh_token=read_secret(account.refresh_token_env),
        token_uri=TOKEN_URI,
        client_id=read_secret(account.client_id_env),
        client_secret=read_secret(account.client_secret_env),
        scopes=SCOPES,
    )


def _status(post: YouTubePost, publish_at: datetime, now: datetime) -> dict[str, Any]:
    """The status to upload with: private until `publish_at`, public once it has passed."""
    status = {
        "selfDeclaredMadeForKids": post.made_for_kids,
        "containsSyntheticMedia": post.contains_synthetic_media,
    }
    if publish_at <= now:
        return {"privacyStatus": "public", **status}
    # YouTube accepts `publishAt` on a private video only, and makes it public at that time.
    return {"privacyStatus": "private", "publishAt": _rfc3339(publish_at), **status}


def _upload(youtube: Client, post: YouTubePost, path: Path, status: dict[str, Any]) -> str:
    snippet = {"title": post.title, "description": post.description, "categoryId": post.category_id}
    media = MediaFileUpload(str(path), mimetype="video/mp4", chunksize=-1, resumable=True)
    request = youtube.videos().insert(
        part="snippet,status", body={"snippet": snippet, "status": status}, media_body=media
    )
    response = None
    while response is None:
        _, response = request.next_chunk()
    return str(response["id"])


def _confirm(youtube: Client, state: PostState) -> PostState:
    """The post once `publish_at` is reached: `published` when the video is public, unchanged while
    YouTube has yet to publish it, `rejected` when it is no longer on the channel or no longer scheduled."""
    items = youtube.videos().list(part="status", id=state.remote_id).execute().get("items", [])
    if not items:
        return dataclasses.replace(
            state,
            status=Status.REJECTED,
            error=f"video {state.remote_id} is no longer on the channel",
        )
    status = items[0]["status"]
    if status["privacyStatus"] == "public":
        return _settled(state, str(state.remote_id), status)
    if status.get("publishAt"):
        return state
    return dataclasses.replace(
        state,
        status=Status.REJECTED,
        error=f"video {state.remote_id} is no longer scheduled on YouTube",
    )


def _settled(state: PostState, video_id: str, status: dict[str, Any]) -> PostState:
    published = status["privacyStatus"] == "public"
    return dataclasses.replace(
        state,
        status=Status.PUBLISHED if published else Status.SCHEDULED,
        remote_id=video_id,
        error=None,
        extra={},
    )


def _find_upload(youtube: Client, post: YouTubePost, publish_at: datetime) -> dict[str, Any] | None:
    """The recent upload of the channel that carries the post's title and was scheduled at `publish_at`,
    or published after it when uploaded late; none if the upload did not reach YouTube."""
    uploads = _own_channel(youtube, "contentDetails")["contentDetails"]["relatedPlaylists"]["uploads"]
    items = (
        youtube.playlistItems()
        .list(
            part="contentDetails",
            playlistId=uploads,
            maxResults=RECENT_UPLOADS,
        )
        .execute()
        .get("items", [])
    )
    ids = [item["contentDetails"]["videoId"] for item in items]
    if not ids:
        return None
    videos = youtube.videos().list(part="snippet,status", id=",".join(ids)).execute().get("items", [])
    for video in videos:
        if video["snippet"]["title"] != post.title:
            continue
        scheduled = video["status"].get("publishAt")
        if scheduled and datetime.fromisoformat(scheduled) == publish_at:
            return dict(video)
        if not scheduled and datetime.fromisoformat(video["snippet"]["publishedAt"]) >= publish_at:
            return dict(video)
    return None


def _check_handle(youtube: Client, handle: str) -> None:
    found = _own_channel(youtube, "snippet")["snippet"].get("customUrl", "").lstrip("@")
    if found.lower() != handle.lstrip("@").lower():
        raise ValueError(f"the token authorizes @{found}, not {handle}: issue a token for the right channel")


def _own_channel(youtube: Client, part: str) -> dict[str, Any]:
    items = youtube.channels().list(part=part, mine=True).execute().get("items", [])
    if not items:
        raise ValueError("the authorized Google account has no YouTube channel")
    return dict(items[0])


def _build(creds: Credentials) -> Client:
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


def _rfc3339(when: datetime) -> str:
    return when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
