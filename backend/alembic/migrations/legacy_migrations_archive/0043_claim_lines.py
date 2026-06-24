"""SC-002 — add claim_lines for multi-line carrier claims.

Revision ID: 0043
Revises: 0042
Create Date: 2026-06-23

A claim today is one lump claimed_amount. Real carrier claims often have
multiple line items (e.g. 3 damaged boxes at different values). This adds
an append-style child table — claims.claimed_amount remains the
authoritative total (sum of lines when lines are present, or the
single value when a claim has no line breakdown).
"""
from alembic import op

revision      = "0043"
down_revision = "0042"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS claim_lines (
            id              UUID PRIMARY KEY,
            tenant_id       UUID NOT NULL REFERENCES tenants(id),
            claim_id        UUID NOT NULL REFERENCES claims(id),
            line_number     INTEGER NOT NULL,
            description     TEXT NOT NULL DEFAULT '',
            claimed_amount  NUMERIC NOT NULL,
            currency        TEXT NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_claim_lines_claim_line ON claim_lines(claim_id, line_number)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_claim_lines_tenant ON claim_lines(tenant_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS claim_lines")
