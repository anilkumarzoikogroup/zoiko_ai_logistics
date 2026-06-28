"""Migration 0010 — SC-004 Runtime Schema.

Adds governance_tasks table and runtime columns needed by SC-003/SC-004
governed spine handlers (task_id, token_id columns on scorecard_periods, etc.).

Revision ID: 0010_sc004_runtime_schema
Revises: 0009_sc004_governed_spine
Create Date: 2026-06-26
"""
from __future__ import annotations

import os
from alembic import op

revision      = "0010_sc004_runtime_schema"
down_revision = "0009_sc004_governed_spine"
branch_labels = None
depends_on    = None

_HERE     = os.path.dirname(os.path.abspath(__file__))
_SQL_FILE = os.path.join(_HERE, "0010_sc004_runtime_schema.sql")


def upgrade() -> None:
    with open(_SQL_FILE, encoding="utf-8") as f:
        op.execute(f.read())


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS governance_tasks CASCADE")
