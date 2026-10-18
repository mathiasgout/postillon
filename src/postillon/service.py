"""The service loop: lists each project's manifests, keeps their states, and hands every post
that needs work to its platform's adapter (see docs/state.md).

Only writer of the states; it keeps them in memory between passes and reads the bucket
again only for a new or changed manifest.
"""

from __future__ import annotations

import bisect
import dataclasses
import hashlib
import logging
import tempfile
import time
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Self

from postillon.adapter import Adapter, Task, Video, load_adapter
from postillon.bucket import Bucket, connect_from_env
from postillon.config import Config
from postillon.entry import Entry
from postillon.platforms.base import Post
from postillon.state import EntryState, PostState, Status

log = logging.getLogger(__name__)

# Statuses of a post whose platform holds the video: the bucket copy is no longer needed.
HOLDS_VIDEO = {Status.SCHEDULED, Status.PUBLISHED}
# Every new YouTube upload counts against a daily quota shared by the channels of a Google Cloud
# project: a lasting failure retried each minute would exhaust it within hours.
RETRY_FIRST = timedelta(minutes=1)
RETRY_MAX = timedelta(hours=1)


@dataclasses.dataclass(frozen=True)
class Manifest:
    etag: str
    sha256: str
    entry: Entry | None
    error: str | None


class ProjectRunner:
    """The entries of one project, with the adapters and accounts its configuration declares."""

    def __init__(self, bucket: Bucket, adapters: dict[str, Adapter], accounts: dict[str, set[str]]):
        self.bucket = bucket
        self.adapters = adapters
        self.accounts = accounts
        self._manifests: dict[str, Manifest] = {}
        self._states: dict[str, EntryState] = {}

    def run_pass(self, now: datetime, workdir: Path) -> None:
        listed = self.bucket.list_manifests()
        for gone in set(self._manifests) - set(listed):
            del self._manifests[gone]
            self._states.pop(gone, None)
        manifests = {}
        for entry_id, etag in sorted(listed.items()):
            try:
                manifest = self._manifests.get(entry_id)
                if manifest is None or manifest.etag != etag:
                    manifest = self._read_manifest(entry_id, etag)
            except Exception:
                log.exception("%s/%s: reading the manifest failed", self.bucket.project, entry_id)
                continue
            if manifest is not None:
                manifests[entry_id] = manifest
        slots = _slots(manifests.values())
        for entry_id, manifest in manifests.items():
            try:
                self._run_entry(
                    entry_id, manifest, now, slots, workdir / hashlib.sha256(entry_id.encode()).hexdigest()[:16],
                )
            except Exception:
                log.exception("%s/%s: pass failed", self.bucket.project, entry_id)

    def _run_entry(
        self, entry_id: str, manifest: Manifest, now: datetime, slots: dict[tuple[str, str], list[datetime]],
        workdir: Path,
    ) -> None:
        state = self._states.get(entry_id)
        if state is None:
            raw = self.bucket.read_state(entry_id)
            state = EntryState.from_json(raw) if raw else EntryState()
            self._states[entry_id] = state
        before = state.to_json()
        changed = state.manifest_sha256 != manifest.sha256
        state.manifest_sha256 = manifest.sha256
        state.error = manifest.error
        if manifest.error and changed:
            log.warning("%s/%s: manifest rejected: %s", self.bucket.project, entry_id, manifest.error)
        if manifest.entry is not None:
            video = Video(self.bucket, entry_id, workdir)
            for post in manifest.entry.posts:
                next_publish_at = _next_slot(slots[post.name, post.account], manifest.entry.publish_at)
                self._run_post(manifest, post, state, now, video, changed, next_publish_at)
        if state.to_json() == before:
            return
        self.bucket.write_state(entry_id, state.to_json())
        # After the state, so that a crash in between leaves a video rather than a lost state.
        if manifest.entry is not None and all(
            state.posts[post.name].status in HOLDS_VIDEO for post in manifest.entry.posts
        ):
            self.bucket.delete_video(entry_id)

    def _read_manifest(self, entry_id: str, etag: str) -> Manifest | None:
        raw = self.bucket.read_manifest(entry_id)
        if raw is None:
            return None
        try:
            entry, error = Entry.from_manifest(entry_id, raw), None
        except ValueError as e:
            entry, error = None, str(e)
        manifest = Manifest(etag=etag, sha256=hashlib.sha256(raw).hexdigest(), entry=entry, error=error)
        self._manifests[entry_id] = manifest
        return manifest

    def _run_post(
        self, manifest: Manifest, post: Post, state: EntryState, now: datetime, video: Video, changed: bool,
        next_publish_at: datetime | None,
    ) -> None:
        entry = manifest.entry
        current = state.posts.get(post.name, PostState())
        if current.status in HOLDS_VIDEO and changed:
            log.warning("%s/%s %s: %s, change ignored", self.bucket.project, entry.id, post.name, current.status)
        if current.status == Status.PUBLISHED:
            return
        if not _needs_step(current, manifest.sha256, entry.publish_at, now):
            return

        def checkpoint(new: PostState) -> None:
            state.posts[post.name] = _stamp(state.posts.get(post.name, current), new, manifest.sha256, now)
            self.bucket.write_state(entry.id, state.to_json())

        if post.account not in self.accounts.get(post.name, set()):
            new = dataclasses.replace(
                current, status=Status.REJECTED, error=f"account {post.account!r} is not configured for {post.name}",
            )
        else:
            task = Task(
                entry=entry, post=post, state=current, now=now, video=video, checkpoint=checkpoint,
                next_publish_at=next_publish_at,
            )
            try:
                new = self.adapters[post.name].step(task)
            except Exception as e:
                log.exception("%s/%s %s: step failed", self.bucket.project, entry.id, post.name)
                # From the last checkpoint, whose fields tell the adapter what may have reached the platform.
                new = dataclasses.replace(
                    state.posts.get(post.name, current), status=Status.FAILED, error=f"{type(e).__name__}: {e}",
                )
        new = dataclasses.replace(new, failures=current.failures + 1 if new.status == Status.FAILED else 0)
        previous = state.posts.get(post.name, current)
        state.posts[post.name] = _stamp(previous, new, manifest.sha256, now)
        if new.status != previous.status:
            log.info(
                "%s/%s %s: %s -> %s%s", self.bucket.project, entry.id, post.name, previous.status, new.status,
                f" ({new.error})" if new.error else "",
            )


class Service:
    def __init__(self, runners: list[ProjectRunner]):
        self.runners = runners

    @classmethod
    def from_config(cls, config: Config) -> Self:
        """The service of the configured projects; raises ValueError when a bucket variable,
        a platform's extra or an account setting is missing."""
        client, name = connect_from_env()
        runners = []
        for project, platforms in config.projects.items():
            adapters = {platform: load_adapter(platform, accounts) for platform, accounts in platforms.items()}
            accounts = {platform: set(accounts) for platform, accounts in platforms.items()}
            runners.append(ProjectRunner(Bucket(client, name, project), adapters, accounts))
        return cls(runners)

    def run_pass(self, now: datetime | None = None) -> None:
        now = now or datetime.now(UTC)
        with tempfile.TemporaryDirectory(prefix="postillon-") as workdir:
            for runner in self.runners:
                try:
                    runner.run_pass(now, Path(workdir) / runner.bucket.project)
                except Exception:
                    log.exception("%s: pass failed", runner.bucket.project)

    def run_forever(self, poll_seconds: int) -> None:
        while True:
            self.run_pass()
            time.sleep(poll_seconds)


def _needs_step(current: PostState, sha256: str, publish_at: datetime, now: datetime) -> bool:
    """Whether the adapter has something to do: a `rejected` post waits for a new manifest, a
    `failed` one for its retry delay or a new manifest, and a `scheduled` one for its
    publication time, to confirm it."""
    if current.status == Status.REJECTED:
        return current.manifest_sha256 != sha256
    if current.status == Status.FAILED and current.manifest_sha256 == sha256 and current.updated_at:
        return now >= current.updated_at + _retry_delay(current.failures)
    if current.status == Status.SCHEDULED:
        return now >= publish_at
    return True


def _retry_delay(failures: int) -> timedelta:
    """1, 2, 4... minutes after the last of `failures` consecutive failures, one hour at most."""
    return min(RETRY_FIRST * 2 ** (min(max(failures, 1), 7) - 1), RETRY_MAX)


def _slots(manifests: Iterable[Manifest]) -> dict[tuple[str, str], list[datetime]]:
    """The sorted `publish_at` of the valid entries, per platform and account."""
    slots = defaultdict(list)
    for manifest in manifests:
        if manifest.entry is not None:
            for post in manifest.entry.posts:
                slots[post.name, post.account].append(manifest.entry.publish_at)
    return {key: sorted(times) for key, times in slots.items()}


def _next_slot(times: list[datetime], publish_at: datetime) -> datetime | None:
    i = bisect.bisect_right(times, publish_at)
    return times[i] if i < len(times) else None


def _stamp(previous: PostState, new: PostState, sha256: str, now: datetime) -> PostState:
    """The adapter's state with the manifest it reflects, dated when it differs from the previous one; a
    post whose platform holds the video keeps reflecting the manifest it was sent with."""
    if new.status not in (Status.FAILED, Status.REJECTED):
        new = dataclasses.replace(new, error=None)
    if previous.status in HOLDS_VIDEO:
        sha256 = previous.manifest_sha256
    new = dataclasses.replace(new, manifest_sha256=sha256, updated_at=previous.updated_at)
    if new != previous:
        new = dataclasses.replace(new, updated_at=now)
    return new
