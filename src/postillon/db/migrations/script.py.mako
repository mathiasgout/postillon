## A migration imports nothing from postillon, whose models change after it, and writes only to
## the database: `migrate` runs it in one transaction, which a file moved on disk would escape.
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
"""

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
