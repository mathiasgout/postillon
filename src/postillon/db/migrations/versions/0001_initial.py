"""Entries, posts and their events.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

STATUS = sa.Enum(
    "PENDING",
    "IN_PROGRESS",
    "SCHEDULED",
    "PUBLISHED",
    "FAILED",
    "REJECTED",
    name="status",
    native_enum=False,
    length=20,
)


def upgrade() -> None:
    op.create_table(
        "entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project", sa.String(100), nullable=False),
        sa.Column("key", sa.String(200), nullable=False),
        sa.Column("publish_at", sa.DateTime(), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("video_released_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("project", "key"),
    )
    op.create_index("ix_entries_publish_at", "entries", ["publish_at"])
    op.create_table(
        "posts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entry_id", sa.Integer(), sa.ForeignKey("entries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("account", sa.String(100), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("status", STATUS, nullable=False),
        sa.Column("remote_id", sa.String(200), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("extra", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("entry_id", "platform"),
    )
    op.create_index("ix_posts_status", "posts", ["status"])
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("post_id", sa.Integer(), sa.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", STATUS, nullable=False),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_events_post_id", "events", ["post_id"])


def downgrade() -> None:
    op.drop_table("events")
    op.drop_table("posts")
    op.drop_table("entries")
