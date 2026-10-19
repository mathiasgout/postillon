from datetime import datetime, timedelta

import pytest

from postillon.domain import PostState
from postillon.platforms.base import Task
from postillon.services.credentials import renew_credentials
from postillon.worker.main import DailyJobs
from tests.support import BEFORE


def test_daily_job_runs_once_a_day():
    runs: list[datetime] = []
    jobs = DailyJobs({"job": runs.append})
    jobs.run_due(BEFORE)
    jobs.run_due(BEFORE + timedelta(hours=1))
    jobs.run_due(BEFORE + timedelta(days=1))
    assert runs == [BEFORE, BEFORE + timedelta(days=1)]


def test_failed_daily_job_runs_again_after_the_next_pass(caplog: pytest.LogCaptureFixture):
    runs: list[datetime] = []

    def flaky(now: datetime) -> None:
        runs.append(now)
        if len(runs) == 1:
            raise ConnectionError("bucket unreachable")

    jobs = DailyJobs({"backup": flaky, "other": lambda now: None})
    jobs.run_due(BEFORE)
    jobs.run_due(BEFORE + timedelta(minutes=1))
    jobs.run_due(BEFORE + timedelta(minutes=2))
    assert len(runs) == 2
    assert "backup failed" in caplog.text


class Renewing:
    def __init__(self) -> None:
        self.renewed: list[datetime] = []

    def step(self, task: Task) -> PostState:
        return task.state

    def renew_credentials(self, now: datetime) -> None:
        self.renewed.append(now)


class Plain:
    def step(self, task: Task) -> PostState:
        return task.state


def test_credentials_are_renewed_on_the_platforms_that_expire():
    first, second = Renewing(), Renewing()
    renew_credentials({"a": {"instagram": first, "youtube": Plain()}, "b": {"instagram": second}}, BEFORE)
    assert first.renewed == second.renewed == [BEFORE]
