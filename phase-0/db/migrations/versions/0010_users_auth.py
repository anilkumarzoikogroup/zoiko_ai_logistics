"""Add users table for real authentication.

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-29

Each tenant has their own users (analysts, managers, admins).
Password stored as bcrypt hash — never plain text.
"""
from __future__ import annotations
from alembic import op

revision      = "0010"
down_revision = "0009"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id     UUID        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            email         TEXT        NOT NULL,
            password_hash TEXT        NOT NULL,
            full_name     TEXT        NOT NULL DEFAULT '',
            role          TEXT        NOT NULL DEFAULT 'analyst'
                            CHECK (role IN ('analyst', 'manager', 'admin')),
            is_active     BOOLEAN     NOT NULL DEFAULT TRUE,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (email)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_tenant
            ON users (tenant_id, role)
            WHERE is_active = TRUE
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_users_tenant")
    op.execute("DROP TABLE IF EXISTS users")
