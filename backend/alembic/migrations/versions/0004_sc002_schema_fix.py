"""SC-002 schema catch-up: idempotent fix for DBs where migration 0002 failed.

The original integration_schema.sql used PostgreSQL-17-only syntax
(ALTER TABLE … ADD CONSTRAINT … NOT NULL col) which caused the entire
migration transaction to roll back on PostgreSQL 13-16.  This migration
re-applies all SC-002 schema objects using standard PostgreSQL 13+ syntax
and CREATE … IF NOT EXISTS / DO $$ … $$ patterns so it is safe to run
on any DB state.

Revision ID: 0004_sc002_fix
Revises: 0003_payment_confirmation
Create Date: 2026-06-25
"""
from __future__ import annotations

import os
from alembic import op

revision      = "0004_sc002_fix"
down_revision = "0003_payment_confirmation"
branch_labels = None
depends_on    = None

_HERE     = os.path.dirname(os.path.abspath(__file__))
_SQL_FILE = os.path.join(_HERE, "sc002_schema_fix.sql")


def upgrade() -> None:
    with open(_SQL_FILE, encoding="utf-8") as f:
        op.execute(f.read())


def downgrade() -> None:
    # Only remove objects that 0004 might have added on top of 0002.
    # If 0002 ran cleanly these are no-ops.
    pass
