"""Add carriers table for carrier contact management.

Revision ID: 0018
Revises: 0017
Create Date: 2026-06-09
"""
from __future__ import annotations
from alembic import op

revision      = "0018"
down_revision = "0017"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS carriers (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            name            TEXT NOT NULL,
            email           TEXT NOT NULL DEFAULT '',
            address         TEXT NOT NULL DEFAULT '',
            contact_person  TEXT NOT NULL DEFAULT '',
            contact_phone   TEXT NOT NULL DEFAULT '',
            cc_emails       TEXT NOT NULL DEFAULT '',
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (tenant_id, name)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS carriers")
