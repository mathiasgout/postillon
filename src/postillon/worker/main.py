"""The worker process: a publishing pass at a fixed interval, and daily jobs (the backup, the
check of the credentials), until SIGTERM (see docs/run-the-service.md).

A stop request ends the loop after the current pass; systemd's stop timeout bounds the wait,
and a pass cut short leaves `in_progress` posts that the next start resolves.
"""

from __future__ import annotations

import logging
import signal
import threading
from collections.abc import Callable
from datetime import UTC, date, datetime
from types import FrameType

from postillon.db.session import check_schema, connect, sessions
from postillon.platforms.loader import load_platforms
from postillon.services.backup import back_up
from postillon.services.credentials import check_credentials
from postillon.services.publishing import Publisher
from postillon.settings import Settings
from postillon.storage.bucket import Bucket
from postillon.storage.videos import VideoStore

log = logging.getLogger(__name__)


def run(settings: Settings) -> None:
    """Runs until stopped; raises ValueError before the first pass when the database, a platform's
    extra or a secret is not ready."""
    engine = connect(settings.database)
    check_schema(engine)
    platforms = {name: load_platforms(project) for name, project in settings.projects.items()}
    bucket = Bucket.connect(settings.bucket)
    videos = VideoStore(settings.videos_dir, settings.max_video_bytes)
    publisher = Publisher(sessions(engine), settings, platforms, videos, bucket)

    stop = threading.Event()

    def request_stop(signum: int, frame: FrameType | None) -> None:
        log.info("stopping after the current pass")
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    daily = DailyJobs(
        {
            "backup": lambda now: back_up(settings.database, bucket, now.date()),
            "credentials check": lambda now: check_credentials(platforms, now),
        }
    )
    while not stop.is_set():
        now = datetime.now(UTC)
        publisher.run_pass(now)
        daily.run_due(now)
        stop.wait(settings.poll_seconds)


class DailyJobs:
    """Jobs run after the first pass of each day, in UTC, and after each start; a job that fails
    runs again after the next pass."""

    def __init__(self, jobs: dict[str, Callable[[datetime], None]]):
        self.jobs = jobs
        self._done_on: dict[str, date] = {}

    def run_due(self, now: datetime) -> None:
        for name, job in self.jobs.items():
            if self._done_on.get(name) == now.date():
                continue
            try:
                job(now)
            except Exception:
                log.exception("%s failed, tried again after the next pass", name)
            else:
                self._done_on[name] = now.date()
