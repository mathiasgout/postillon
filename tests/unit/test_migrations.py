from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine, text

from postillon.db.models import Base
from postillon.db.session import check_schema, connect, migrate


def test_migrations_build_the_schema_of_the_models(engine: Engine):
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"render_as_batch": True})
        assert compare_metadata(context, Base.metadata) == []
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1


@pytest.fixture
def bare_engine(tmp_path: Path) -> Iterator[Engine]:
    engine = connect(tmp_path / "postillon.db")
    yield engine
    engine.dispose()


def test_a_database_of_another_schema_history_is_refused(bare_engine: Engine):
    with bare_engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(text("INSERT INTO alembic_version VALUES ('0001')"))
    with pytest.raises(ValueError, match="run `postillon migrate`"):
        check_schema(bare_engine)
    with pytest.raises(ValueError, match=r"cannot migrate this database.*0001"):
        migrate(bare_engine)


def test_a_failed_migration_leaves_no_table(bare_engine: Engine, monkeypatch: pytest.MonkeyPatch):
    upgrade = command.upgrade

    def interrupted(config: Config, revision: str) -> None:
        upgrade(config, revision)
        raise RuntimeError("interrupted")

    monkeypatch.setattr(command, "upgrade", interrupted)
    with pytest.raises(RuntimeError, match="interrupted"):
        migrate(bare_engine)
    with bare_engine.connect() as connection:
        assert connection.execute(text("SELECT name FROM sqlite_master WHERE type = 'table'")).all() == []
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
