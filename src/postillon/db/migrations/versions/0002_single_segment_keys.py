"""Single-segment keys, the video as a state of the entry, the entry's version and the publication
time of each post.

Moves each held video to `<project>/<key>.<sha256>.mp4` under the videos folder `migrate` hands
over; run with the worker stopped. Cannot be undone: restore a backup instead.

Revision ID: 0002
Revises: 0001
"""

import hashlib
import os
from pathlib import Path

import sqlalchemy as sa
from alembic import context, op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

CHUNK_BYTES = 1024 * 1024


def upgrade() -> None:
    with op.batch_alter_table("entries") as batch:
        batch.add_column(sa.Column("video_received_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("video_size", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("video_sha256", sa.String(64), nullable=True))
        batch.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    with op.batch_alter_table("entries") as batch:
        batch.alter_column("version", server_default=None)
    with op.batch_alter_table("posts") as batch:
        batch.add_column(sa.Column("publish_at", sa.DateTime(), nullable=True))
    connection = op.get_bind()
    connection.execute(
        sa.text("UPDATE posts SET publish_at = (SELECT publish_at FROM entries WHERE entries.id = posts.entry_id)")
    )
    with op.batch_alter_table("posts") as batch:
        batch.alter_column("publish_at", existing_type=sa.DateTime(), nullable=False)
    videos_dir = context.config.attributes["videos_dir"]
    for entry_id, project, key, released in connection.execute(
        sa.text("SELECT id, project, key, video_released_at FROM entries ORDER BY id")
    ).all():
        new_key = key.replace("/", "-")
        if new_key != key:
            _rename(connection, entry_id, project, new_key)
        if released is None:
            _record_video(connection, entry_id, videos_dir / project, key, new_key)


def downgrade() -> None:
    raise RuntimeError("0002 renames keys and moves videos: restore a backup taken before it")


def _rename(connection: sa.Connection, entry_id: int, project: str, new_key: str) -> None:
    taken = connection.execute(
        sa.text("SELECT 1 FROM entries WHERE project = :project AND key = :key"), {"project": project, "key": new_key}
    ).first()
    if taken:
        raise RuntimeError(f"{project}/{new_key} exists already: rename one of the two entries first")
    connection.execute(sa.text("UPDATE entries SET key = :key WHERE id = :id"), {"key": new_key, "id": entry_id})


def _record_video(connection: sa.Connection, entry_id: int, folder: Path, key: str, new_key: str) -> None:
    """Fills the video state from the held file and moves it to its new name; an entry whose file is
    missing keeps no video, and its pending posts wait for one."""
    old = folder / f"{key}.mp4"
    if not old.exists():
        return
    digest = hashlib.sha256()
    size = 0
    with old.open("rb") as f:
        while chunk := f.read(CHUNK_BYTES):
            digest.update(chunk)
            size += len(chunk)
    sha256 = digest.hexdigest()
    connection.execute(
        sa.text(
            "UPDATE entries SET video_received_at = updated_at, video_size = :size, video_sha256 = :sha256"
            " WHERE id = :id"
        ),
        {"size": size, "sha256": sha256, "id": entry_id},
    )
    os.replace(old, folder / f"{new_key}.{sha256}.mp4")
    # The folders of the former key segments, once empty.
    for parent in old.parents:
        if parent == folder:
            break
        if not any(parent.iterdir()):
            parent.rmdir()
