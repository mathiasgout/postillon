"""The Instagram adapter: publishes each video as a Reel at `publish_at`, across passes, and
renews the accounts' tokens (see docs/instagram.md).

Only module that talks to Instagram, through the Instagram API with Instagram Login, and
only writer of the token file.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Self
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from postillon import environment
from postillon.adapter import Task
from postillon.platforms.instagram.post import Instagram
from postillon.state import PostState, Status

log = logging.getLogger(__name__)

API = "https://graph.instagram.com"
API_VERSION = "v25.0"
TIMEOUT_SECONDS = 60
# Instagram fetches the video while it processes the container, within minutes.
VIDEO_URL_SECONDS = 3600
# A refresh needs a token at least 24 hours old and makes it valid 60 days: weekly leaves margin.
REFRESH_AFTER = timedelta(days=7)
# Relative to the working directory, next to `.env`.
TOKENS_FILE = Path("instagram-tokens.json")
# Set on the state between the creation of the Reel container and its publication.
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


@dataclasses.dataclass(frozen=True)
class Account:
    username: str
    access_token_env: str

    @classmethod
    def from_settings(cls, name: str, settings: dict[str, Any]) -> Self:
        """The account read from its configuration; raises ValueError on an unknown, missing or non-string setting."""
        fields = {f.name for f in dataclasses.fields(cls)}
        unknown = sorted(set(settings) - fields)
        if unknown:
            raise ValueError(f"instagram account {name}: unknown settings {unknown}")
        missing = sorted(fields - set(settings))
        if missing:
            raise ValueError(f"instagram account {name}: missing settings {missing}")
        for key, value in settings.items():
            if not isinstance(value, str) or not value:
                raise ValueError(f"instagram account {name}: {key} must be a non-empty string")
        return cls(**settings)


class Tokens:
    """The renewed token of each account, by the variable that holds its first token in `.env`. A
    renewed token is used only while that variable keeps the token it was renewed from, so that a
    token the operator places in `.env` wins."""

    def __init__(self, path: Path):
        self.path = path

    def current(self, variable: str, seed: str) -> tuple[str, datetime | None]:
        """The token to use and when it was last renewed, never for the seed itself."""
        record = self._read().get(variable)
        if record and record["seed_sha256"] == _sha256(seed):
            return record["token"], datetime.fromisoformat(record["refreshed_at"])
        return seed, None

    def save(self, variable: str, seed: str, token: str, refreshed_at: datetime) -> None:
        data = self._read()
        data[variable] = {"seed_sha256": _sha256(seed), "token": token, "refreshed_at": refreshed_at.isoformat()}
        partial = self.path.with_name(self.path.name + ".tmp")
        fd = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        # Replaced at once, so that a crash never leaves a truncated file and loses the tokens.
        os.replace(partial, self.path)

    def _read(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text())
        except FileNotFoundError:
            return {}


class Adapter:
    def __init__(self, accounts: dict[str, dict[str, Any]], tokens: Path = TOKENS_FILE):
        self._accounts = {name: Account.from_settings(name, settings) for name, settings in accounts.items()}
        # Fails at start on a missing secret rather than on the first post.
        for account in self._accounts.values():
            environment.variable(account.access_token_env)
        self._tokens = Tokens(tokens)
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
        post: Instagram = task.post
        state = task.state
        token = self._token(post.account, task.now)
        user_id = self._user_id(post.account, token)
        container = state.extra.get(CONTAINER)
        if container is None:
            if task.now < task.entry.publish_at:
                return state
            # After an interruption, only the last missed Reel of the account goes out, rather than all at once.
            if task.next_publish_at is not None and task.now >= task.next_publish_at:
                return dataclasses.replace(
                    state, status=Status.REJECTED, error=f"missed: the account's next Reel was due at "
                    f"{task.next_publish_at:%Y-%m-%dT%H:%M:%SZ}", extra={},
                )
            container = _create_container(user_id, post, task.video.url(VIDEO_URL_SECONDS), token)
            return dataclasses.replace(state, status=Status.IN_PROGRESS, error=None, extra={CONTAINER: container})
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
                    state, status=Status.FAILED, error=f"container {container} expired before publication", extra={},
                )
            case code:
                return dataclasses.replace(
                    state, status=Status.REJECTED, error=f"Instagram could not process the video ({code}: "
                    f"{status.get('status', 'no detail')})", extra={},
                )

    def _token(self, name: str, now: datetime) -> str:
        """The account's token, renewed when due; a failed renewal keeps the current token and is
        tried again after `REFRESH_AFTER`."""
        variable = self._accounts[name].access_token_env
        seed = environment.variable(variable)
        token, refreshed_at = self._tokens.current(variable, seed)
        if refreshed_at is not None and now - refreshed_at < REFRESH_AFTER:
            return token
        try:
            token = _refresh(token)
        except (GraphError, OSError) as e:
            log.warning("instagram account %s: token not renewed: %s", name, e)
        self._tokens.save(variable, seed, token, now)
        return token

    def _user_id(self, name: str, token: str) -> str:
        """The account's Instagram user identifier; raises ValueError when the token belongs to another account."""
        if name not in self._users:
            me = _request("GET", "me", {"fields": "user_id,username"}, token)
            expected = self._accounts[name].username.lstrip("@")
            if me["username"].lower() != expected.lower():
                raise ValueError(f"the token authorizes {me['username']}, not {expected}: place the right token in .env")
            self._users[name] = me["user_id"]
        return self._users[name]


def _create_container(user_id: str, post: Instagram, video_url: str, token: str) -> str:
    params = {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": post.caption,
        "share_to_feed": "true" if post.share_to_feed else "false",
        "thumb_offset": str(post.thumb_offset),
    }
    return _request("POST", f"{user_id}/media", params, token)["id"]


def _refresh(token: str) -> str:
    query = urlencode({"grant_type": "ig_refresh_token", "access_token": token})
    return _send(Request(f"{API}/refresh_access_token?{query}"))["access_token"]


def _request(method: str, path: str, params: dict[str, str], token: str) -> dict[str, Any]:
    """The JSON response of a Graph API call; raises GraphError when Instagram refuses it."""
    url = f"{API}/{API_VERSION}/{path}"
    body = urlencode(params).encode()
    if method == "GET":
        url, body = f"{url}?{body.decode()}", None
    return _send(Request(url, data=body, method=method, headers={"Authorization": f"Bearer {token}"}))


def _send(request: Request) -> dict[str, Any]:
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.load(response)
    except HTTPError as e:
        try:
            error = json.loads(e.read()).get("error", {})
        except ValueError:
            error = {}
        raise GraphError(e.code, error if isinstance(error, dict) else {}) from None


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
