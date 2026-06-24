"""Add api_keys table for tenant API key management.

Revision ID: 0026
Revises: 0025
Create Date: 2026-06-14

Settings -> API Keys lets an admin generate a key for programmatic
access. Only the SHA-256 hash of the key is stored; the full key is
shown once at creation time.
"""
from __future__ import annotations
from alembic import op

revision      = "0026"
down_revision = "0025"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id     UUID        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            name          TEXT        NOT NULL,
            key_prefix    TEXT        NOT NULL,
            key_hash      TEXT        NOT NULL,
            scopes        TEXT        NOT NULL DEFAULT 'read:*',
            created_by    TEXT        NOT NULL,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_used_at  TIMESTAMPTZ,
            revoked_at    TIMESTAMPTZ,
            UNIQUE (key_hash)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_api_keys_tenant
            ON api_keys (tenant_id)
            WHERE revoked_at IS NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_api_keys_tenant")
    op.execute("DROP TABLE IF EXISTS api_keys")
