"""Witness packs — snapshot reference data pinned at the moment it was used.

Revision ID: 0040
Revises: 0039
Create Date: 2026-06-20

Distinct from the transparency log (0039): the transparency log proves an
ACR was published. A witness pack proves *which exact version of a piece
of reference data* (e.g. a contract_rates row) was actually read and used
at decision time — so if that row is later superseded, edited, or its
payload_hash check (0038) ever flags tampering, there is still an
independent, signed record of exactly what content was relied upon when
the decision was made.

witness_packs:
  - source_record_id  UUID — the source record whose validation produced this pack
  - subject_type       TEXT — e.g. 'CONTRACT_RATE'
  - subject_id         UUID — the contract_rates.id (or other subject) snapshotted
  - snapshot_payload    JSONB — the subject's content at the moment of use
  - snapshot_hash       BYTEA — SHA-256 domain-tagged hash of snapshot_payload
  - signature / kid     — signed at creation time
"""
from alembic import op

revision      = "0040"
down_revision = "0039"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS witness_packs (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id         UUID NOT NULL REFERENCES tenants(id),
            source_record_id  UUID NOT NULL REFERENCES source_records(id),
            subject_type      TEXT NOT NULL,
            subject_id        UUID NOT NULL,
            snapshot_payload  JSONB NOT NULL,
            snapshot_hash     BYTEA NOT NULL,
            signature         BYTEA NOT NULL,
            kid               TEXT NOT NULL,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_witness_packs_source_record
            ON witness_packs(tenant_id, source_record_id)
    """)
    op.execute("ALTER TABLE witness_packs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE witness_packs FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_witness_packs_source_record")
    op.execute("DROP TABLE IF EXISTS witness_packs")
