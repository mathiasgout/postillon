"""The TikTok client: the operator schedules the video in TikTok Studio and tells the API, the
client only follows the publication time (see docs/tiktok.md)."""

from __future__ import annotations

import dataclasses

from postillon.domain import PostState, Status
from postillon.platforms.base import Task

NOT_SCHEDULED = "not scheduled by the operator before publish_at"


class TikTokPlatform:
    def step(self, task: Task) -> PostState:
        if task.now < task.publish_at:
            return task.state
        if task.state.status == Status.SCHEDULED:
            # Taken on the operator's word: no API reads the account's videos.
            return dataclasses.replace(task.state, status=Status.PUBLISHED)
        return dataclasses.replace(task.state, status=Status.REJECTED, error=NOT_SCHEDULED)
