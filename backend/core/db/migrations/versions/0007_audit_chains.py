"""Audit chains table for ACR replay proof.

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-27

A-13: every ACR can be rebuilt from event history.
audit_chains records the ordered sequence of case_events that produced
each ACR, enabling deterministic replay verification.
"""
from __future__ import annotations
from alembic import op

revision      = "0007"
down_revision = "0006"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE audit_chains (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL REFERENCES tenants(id),
        case_id         UUID NOT NULL REFERENCES cases(id),
        acr_id          UUID,
        chain_root_hash BYTEA NOT NULL,
        event_count     INTEGER NOT NULL DEFAULT 0,
        events_snapshot JSONB NOT NULL DEFAULT '[]',
        sealed_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
        sealed_by       TEXT NOT NULL DEFAULT 'system'
    )""")
    op.execute("ALTER TABLE audit_chains ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_chains FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_chains CASCADE")
