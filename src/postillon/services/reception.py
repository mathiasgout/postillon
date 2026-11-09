"""Records the video a producer sends for an entry as the entry's state (see docs/api.md).

Called by the API, which received the bytes into a staging file, commits, then moves the file into
place: the database says which video the entry holds, the disk only stores it.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime

from postillon.db.models import Entry
from postillon.storage.videos import Staged


@dataclasses.dataclass(frozen=True)
class Received:
    # False when the entry already holds these exact bytes.
    changed: bool
    # The video the service held before, whose file goes once the new one is in place.
    replaced: str | None


def receive(entry: Entry, staged: Staged, now: datetime) -> Received:
    """Makes the staged video the entry's; the posts not sent yet take it, a post that may have
    reached its platform keeps the one it was sent with."""
    if entry.holds_video and entry.video_sha256 == staged.sha256:
        return Received(changed=False, replaced=None)
    replaced = entry.video_sha256 if entry.holds_video else None
    entry.video_received_at = now
    entry.video_size = staged.size
    entry.video_sha256 = staged.sha256
    entry.video_released_at = None
    entry.updated_at = now
    return Received(changed=True, replaced=replaced)
