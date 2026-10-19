from datetime import timedelta

import pytest
from pydantic import ValidationError

from postillon.domain import PostState, Status
from postillon.platforms.base import Task
from postillon.platforms.tiktok import TikTokAccount, TikTokPost
from postillon.platforms.tiktok.client import NOT_SCHEDULED, TikTokPlatform
from tests.support import BEFORE, PUBLISH_AT

POST = TikTokPost(account="main", caption="Day 23 #cooking")


class NoVideo:
    def file(self):
        raise AssertionError("the platform never reads the video")

    def url(self, expires_seconds):
        raise AssertionError("the platform never reads the video")


def step(status: Status, now) -> PostState:
    task = Task(
        post=POST,
        publish_at=PUBLISH_AT,
        state=PostState(status=status),
        now=now,
        video=NoVideo(),
        checkpoint=lambda state: None,
        next_publish_at=None,
    )
    return TikTokPlatform().step(task)


@pytest.mark.parametrize("status", [Status.PENDING, Status.SCHEDULED])
def test_post_is_left_as_it_is_before_its_publication_time(status: Status):
    assert step(status, PUBLISH_AT - timedelta(seconds=1)) == PostState(status=status)


def test_scheduled_post_is_published_at_its_publication_time():
    assert step(Status.SCHEDULED, PUBLISH_AT) == PostState(status=Status.PUBLISHED)


def test_post_not_scheduled_at_its_publication_time_is_rejected():
    assert step(Status.PENDING, BEFORE + timedelta(days=2)) == PostState(status=Status.REJECTED, error=NOT_SCHEDULED)


def test_post_is_manual():
    assert TikTokPost.manual


def test_caption_counts_utf16_units():
    TikTokPost(account="main", caption="a" * 2200)
    TikTokPost(account="main", caption="🍝" * 1100)
    with pytest.raises(ValidationError, match="2202 UTF-16 units, limit 2200"):
        TikTokPost(account="main", caption="🍝" * 1101)


@pytest.mark.parametrize("handle", ["mychannel", "@my channel", "@"])
def test_malformed_handle_is_refused(handle: str):
    with pytest.raises(ValidationError):
        TikTokAccount(handle=handle)
