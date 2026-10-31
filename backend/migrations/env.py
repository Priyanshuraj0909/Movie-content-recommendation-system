"""Alembic environment; credentials are supplied via an existing connection."""

from alembic import context

connection = context.config.attributes.get("connection")
if connection is None:
    raise RuntimeError("Run python scripts/migrate_database.py with DATABASE_URL set")
context.configure(connection=connection, compare_type=True)
with context.begin_transaction():
    context.run_migrations()
