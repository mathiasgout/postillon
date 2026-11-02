"""The Instagram platform: publishes each video as a Reel at `publish_at`, across passes, and
warns before the accounts' tokens lose their data access (see docs/instagram.md).

Only module that talks to Instagram, through the Instagram API with Facebook Login and a Page
access token per account.
"""

from __future__ import annotations

import dataclasses
import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from postillon.domain import PostState, Status
from postillon.platforms.base import Task, read_secret
from postillon.platforms.instagram.post import InstagramPost
from postillon.platforms.instagram.settings import InstagramAccount

log = logging.getLogger(__name__)

API = "https://graph.facebook.com"
API_VERSION = "v25.0"
TIMEOUT_SECONDS = 60
# Instagram fetches the video while it processes the container, within minutes.
VIDEO_URL_SECONDS = 3600
# Meta cuts a token's data access 90 days after the user's last consent; two weeks of warnings
# leave the operator time to consent again.
WARN_BEFORE = timedelta(days=14)
# Kept in the state between the creation of the Reel container and its publication.
CONTAINER = "container_id"
# Graph API error codes worth retrying: temporary failures, rate and publishing limits, and an
# invalid token, which the operator replaces.
RETRYABLE_CODES = {1, 2, 4, 9, 17, 32, 190, 341, 613}


class GraphError(Exception):
    def __init__(self, status: int, error: dict[str, Any]):
        self.status = status
        self.code = error.get("code")
        self.transient = bool(error.get("is_transient"))
        super().__init__(f"Instagram refused ({status} code {self.code}: {error.get('message', 'no message')})")

    @property
    def retryable(self) -> bool:
        return self.status >= 500 or self.status == 429 or self.transient or self.code in RETRYABLE_CODES


class InstagramPlatform:
    def __init__(self, accounts: Mapping[str, InstagramAccount]):
        self._accounts = dict(accounts)
        # Fails at start on a missing secret rather than on the first post.
        for account in self._accounts.values():
            read_secret(account.access_token_env)
        # The Instagram user identifier of each account, once its username is checked.
        self._users: dict[str, str] = {}

    def step(self, task: Task) -> PostState:
        try:
            return self._step(task)
        except GraphError as e:
            if e.retryable:
                raise
            return dataclasses.replace(task.state, status=Status.REJECTED, error=str(e), extra={})

    def _step(self, task: Task) -> PostState:
        post = task.post
        assert isinstance(post, InstagramPost)
        state = task.state
        token = read_secret(self._accounts[post.account].access_token_env)
        user_id = self._user_id(post.account, token)
        container = state.extra.get(CONTAINER)
        if container is None:
            if task.now < task.publish_at:
                return state
            # After an interruption, only the last missed Reel of the account goes out, rather than all at once.
            if task.next_publish_at is not None and task.now >= task.next_publish_at:
                return dataclasses.replace(
                    state,
                    status=Status.REJECTED,
                    error=f"missed: the account's next Reel was due at {task.next_publish_at:%Y-%m-%dT%H:%M:%SZ}",
                    extra={},
                )
            container = _create_container(user_id, post, task.video.url(VIDEO_URL_SECONDS), token)
            return dataclasses.replace(state, status=Status.IN_PROGRESS, error=None, extra={CONTAINER: container})
        return _follow(state, str(container), user_id, token)

    def check_credentials(self, now: datetime) -> None:
        """Logs, for each account, when its token loses its data access: a warning within
        `WARN_BEFORE`, an error once lost or when the token is invalid."""
        for name, account in self._accounts.items():
            token = read_secret(account.access_token_env)
            try:
                info = _request("GET", "debug_token", {"input_token": token}, token)["data"]
            except (GraphError, OSError, KeyError) as e:
                log.warning("instagram account %s: token not checked: %s", name, e)
                continue
            expires_at = datetime.fromtimestamp(info.get("data_access_expires_at", 0), UTC)
            if not info.get("is_valid") or expires_at <= now:
                log.error("instagram account %s: token invalid or data access lost, consent again", name)
            elif expires_at - now <= WARN_BEFORE:
                log.warning("instagram account %s: data access lost on %s, consent again", name, expires_at.date())
            else:
                log.info("instagram account %s: data access until %s", name, expires_at.date())

    def _user_id(self, name: str, token: str) -> str:
        """The Instagram user identifier of the account linked to the token's Page; raises ValueError
        when the token is not a Page token or its Page is linked to another account."""
        if name not in self._users:
            fields = {"fields": "instagram_business_account{id,username}"}
            try:
                page = _request("GET", "me", fields, token)
            except GraphError as e:
                if e.retryable:
                    raise
                raise ValueError(f"the token reads no Instagram account, set a Page access token: {e}") from None
            account = page.get("instagram_business_account")
            expected = self._accounts[name].username
            if account is None:
                raise ValueError(f"the token's Page is linked to no Instagram account, expected {expected}")
            if account["username"].lower() != expected.lower():
                raise ValueError(f"the token authorizes {account['username']}, not {expected}: set the right token")
            self._users[name] = str(account["id"])
        return self._users[name]


def _follow(state: PostState, container: str, user_id: str, token: str) -> PostState:
    """The post after reading its container: unchanged while Instagram processes the video, then
    published, failed when the container expired, or rejected."""
    status = _request("GET", container, {"fields": "status_code,status"}, token)
    match status["status_code"]:
        case "IN_PROGRESS":
            return state
        case "FINISHED":
            media = _request("POST", f"{user_id}/media_publish", {"creation_id": container}, token)
            return dataclasses.replace(state, status=Status.PUBLISHED, remote_id=media["id"], error=None, extra={})
        case "PUBLISHED":
            # Published on an earlier pass whose state was lost; Instagram gives the container, not the media.
            return dataclasses.replace(state, status=Status.PUBLISHED, error=None, extra={})
        case "EXPIRED":
            return dataclasses.replace(
                state,
                status=Status.FAILED,
                error=f"container {container} expired before publication",
                extra={},
            )
        case code:
            return dataclasses.replace(
                state,
                status=Status.REJECTED,
                error=f"Instagram could not process the video ({code}: {status.get('status', 'no detail')})",
                extra={},
            )


def _create_container(user_id: str, post: InstagramPost, video_url: str, token: str) -> str:
    params = {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": post.caption,
        "share_to_feed": "true" if post.share_to_feed else "false",
        "thumb_offset": str(post.thumb_offset),
    }
    return str(_request("POST", f"{user_id}/media", params, token)["id"])


def _request(method: str, path: str, params: dict[str, str], token: str) -> dict[str, Any]:
    """The JSON response of a Graph API call; raises GraphError when Instagram refuses it."""
    url = f"{API}/{API_VERSION}/{path}"
    body: bytes | None = urlencode(params).encode()
    if method == "GET":
        url, body = f"{url}?{urlencode(params)}", None
    return _send(Request(url, data=body, method=method, headers={"Authorization": f"Bearer {token}"}))


def _send(request: Request) -> dict[str, Any]:
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return dict(json.load(response))
    except HTTPError as e:
        try:
            error = json.loads(e.read()).get("error", {})
        except ValueError:
            error = {}
        raise GraphError(e.code, error if isinstance(error, dict) else {}) from None
