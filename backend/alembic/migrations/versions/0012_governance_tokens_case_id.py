"""Migration 0012 — Add case_id to governance_tokens.

SC-003/SC-004/SC-005 governance handlers insert case_id into governance_tokens
so that execution queries can join tokens → cases directly. The column was
missing from the baseline schema.

Revision ID: 0012_governance_tokens_case_id
Revises: 0011_sc005_accessorial_dispute
Create Date: 2026-06-27
"""
from __future__ import annotations

import os
from alembic import op

revision      = "0012_governance_tokens_case_id"
down_revision = "0011_sc005_accessorial_dispute"
branch_labels = None
depends_on    = None

_HERE     = os.path.dirname(os.path.abspath(__file__))
_SQL_FILE = os.path.join(_HERE, "0012_governance_tokens_case_id.sql")


def upgrade() -> None:
    with open(_SQL_FILE, encoding="utf-8") as f:
        op.execute(f.read())


def downgrade() -> None:
    op.execute("ALTER TABLE governance_tokens DROP COLUMN IF EXISTS case_id")
