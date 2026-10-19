"""The daily copy of the database to the bucket (see docs/run-the-service.md).

A lost SD card would otherwise forget the posts in progress, and the worker would upload a
video a platform already holds.
"""

from __future__ import annotations

import sqlite3
import tempfile
from datetime import date
from pathlib import Path

from postillon.storage.bucket import Bucket


def back_up(database: Path, bucket: Bucket, day: date) -> None:
    """Uploads a consistent copy of the database, even while the API or the worker writes."""
    with tempfile.TemporaryDirectory(prefix="postillon-") as workdir:
        copy = Path(workdir) / "backup.sqlite3"
        source, target = sqlite3.connect(database), sqlite3.connect(copy)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        bucket.upload_backup(copy, day)
