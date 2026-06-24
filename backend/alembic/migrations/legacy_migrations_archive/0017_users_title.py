"""Add title column to users table.

Revision ID: 0017
Revises: 0016
Create Date: 2026-06-09
"""
from __future__ import annotations
from alembic import op

revision      = "0017"
down_revision = "0016"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE users
            ADD COLUMN IF NOT EXISTS title TEXT NOT NULL DEFAULT ''
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS title")
