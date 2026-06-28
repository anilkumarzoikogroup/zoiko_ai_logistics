"""Migration 0008 — SC-004 Scorecard Periods schema.

Adds scorecard_periods table and related structures for supplier scorecard
breach detection.

Revision ID: 0008_sc004_scorecard_periods
Revises: 0007_canonical_commercial_tables
Create Date: 2026-06-26
"""
from __future__ import annotations

import os
from alembic import op

revision      = "0008_sc004_scorecard_periods"
down_revision = "0007_canonical_commercial_tables"
branch_labels = None
depends_on    = None

_HERE     = os.path.dirname(os.path.abspath(__file__))
_SQL_FILE = os.path.join(_HERE, "0008_sc004_scorecard_periods.sql")


def upgrade() -> None:
    with open(_SQL_FILE, encoding="utf-8") as f:
        op.execute(f.read())


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS scorecard_periods CASCADE")
