"""The connection to the SQLite database shared by the API and the worker, and the check that its
schema is current (see docs/run-the-service.md).

Both processes write: WAL lets one read while the other writes, and the busy timeout makes a
writer wait for the other rather than fail.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

BUSY_TIMEOUT_MS = 10_000


def connect(path: Path) -> Engine:
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path}")

    @event.listens_for(engine, "connect")
    def _pragmas(connection: Any, record: Any) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        cursor.close()

    return engine


def sessions(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


def migrate(engine: Engine) -> None:
    """Brings the schema to the latest migration."""
    with engine.begin() as connection:
        config = _alembic_config()
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def check_schema(engine: Engine) -> None:
    """Raises ValueError unless the schema is at the latest migration."""
    head = ScriptDirectory.from_config(_alembic_config()).get_current_head()
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    if current != head:
        raise ValueError(f"database schema is at {current}, expected {head}: run `postillon migrate`")


def _alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", "postillon.db:migrations")
    return config
