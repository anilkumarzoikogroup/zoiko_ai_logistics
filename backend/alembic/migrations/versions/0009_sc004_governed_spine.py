"""Migration 0009 — SC-004 Governed Spine.

Extends scorecard_periods with case linkage. Extends cases.case_type to include
SCORECARD_BREACH. Adds scorecard_id to governance_tasks.

Revision ID: 0009_sc004_governed_spine
Revises: 0008_sc004_scorecard_periods
Create Date: 2026-06-26
"""
from __future__ import annotations

import os
from alembic import op

revision      = "0009_sc004_governed_spine"
down_revision = "0008_sc004_scorecard_periods"
branch_labels = None
depends_on    = None

_HERE     = os.path.dirname(os.path.abspath(__file__))
_SQL_FILE = os.path.join(_HERE, "0009_sc004_governed_spine.sql")


def upgrade() -> None:
    with open(_SQL_FILE, encoding="utf-8") as f:
        op.execute(f.read())


def downgrade() -> None:
    pass  # constraint changes are not easily reversed
