"""Add lineage and versioning to contract_rates; add model_calls audit trail.

Revision ID: 0036
Revises: 0035
Create Date: 2026-06-17

Closes the gap between contract_rates and the documented Canonical Truth
spec: rate corrections must version (never overwrite), and every rate
should be traceable to the source document it came from. AI-extracted
rates must also leave a model-call audit trail (input/output hashes) so
extraction is independently verifiable.

contract_rates gains:
  - version             INT      — 1 for a brand-new rate, N+1 when it supersedes a prior version
  - supersedes_id        UUID     — FK to the contract_rates row this version replaces
  - superseded_at        TIMESTAMPTZ — set when a newer version replaces this row; NULL = active
  - source_document_id   UUID     — FK to documents(id), the contract file this rate was read from

New table:
  - model_calls — audit trail for every AI model invocation (prompt/input/output hashes)

Note: clause-level breakdown already exists via contract_clauses
(0019_domain_tables.py, contract_rate_id FK) — no new table needed here.
"""
from alembic import op

revision      = "0036"
down_revision = "0035"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE contract_rates
            ADD COLUMN IF NOT EXISTS version             INTEGER NOT NULL DEFAULT 1,
            ADD COLUMN IF NOT EXISTS supersedes_id        UUID REFERENCES contract_rates(id),
            ADD COLUMN IF NOT EXISTS superseded_at        TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS source_document_id   UUID
    """)

    # Only one active (non-superseded) rate per tenant/carrier/rate_type
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_contract_rates_active
            ON contract_rates(tenant_id, carrier_id, rate_type)
            WHERE superseded_at IS NULL
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS model_calls (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            purpose         TEXT NOT NULL,
            model_id        TEXT NOT NULL,
            model_version   TEXT NOT NULL DEFAULT '',
            prompt_version  TEXT NOT NULL DEFAULT 'v1',
            input_hash      TEXT NOT NULL,
            output_hash     TEXT NOT NULL,
            latency_ms      INTEGER NOT NULL DEFAULT 0,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_model_calls_tenant_purpose
            ON model_calls(tenant_id, purpose, created_at)
    """)
    op.execute("ALTER TABLE model_calls ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE model_calls FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS model_calls")
    op.execute("DROP INDEX IF EXISTS idx_contract_rates_active")
    op.execute("""
        ALTER TABLE contract_rates
            DROP COLUMN IF EXISTS version,
            DROP COLUMN IF EXISTS supersedes_id,
            DROP COLUMN IF EXISTS superseded_at,
            DROP COLUMN IF EXISTS source_document_id
    """)
