"""Runs the migrations on the connection `postillon.db.session.migrate` hands over."""

from alembic import context

from postillon.db.models import Base

connection = context.config.attributes["connection"]
# SQLite alters a table by copying it, which batch mode does.
context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
with context.begin_transaction():
    context.run_migrations()
