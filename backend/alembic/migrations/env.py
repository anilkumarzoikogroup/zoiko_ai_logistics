"""Alembic environment — supports offline and online migration modes."""
from __future__ import annotations

import os
from logging.config import fileConfig

from dotenv import load_dotenv
from alembic import context
from sqlalchemy import pool

# Load .env first so DB_URL is available in both local dev and CI
load_dotenv()

config = context.config

# Substitute DB_URL from environment (env var wins over alembic.ini default)
db_url = os.environ.get("DB_URL")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None  # we use raw SQL migrations, not ORM metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Build engine directly from the URL already resolved in env.py
    # (avoids configparser interpolation issues with %(DB_URL)s in alembic.ini)
    from sqlalchemy import create_engine, text
    url = config.get_main_option("sqlalchemy.url")
    connectable = create_engine(url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        # Serialize concurrent `alembic upgrade head` runs (e.g. parallel CI
        # jobs sharing one Neon DB) so they don't race on alembic_version.
        # Commit immediately after acquiring/releasing — pg_advisory_lock is
        # session-scoped and persists across commits, but leaving these
        # statements in an open transaction would make alembic's own
        # transaction a nested one whose commit doesn't reach the DB.
        connection.execute(text("SELECT pg_advisory_lock(727274)"))
        connection.commit()
        try:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(727274)"))
            connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
