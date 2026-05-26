"""Add OCC version column to cases table (T-016).

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-26

Adds cases.version (INTEGER NOT NULL DEFAULT 1) to enable Optimistic
Concurrency Control on FSM transitions. Every UPDATE increments version;
callers that pass a stale version receive 409 Conflict.
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cases", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    op.drop_column("cases", "version")
