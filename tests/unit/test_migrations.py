from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.util.exc import CommandError
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
    with pytest.raises(CommandError, match="0001"):
        migrate(bare_engine)
