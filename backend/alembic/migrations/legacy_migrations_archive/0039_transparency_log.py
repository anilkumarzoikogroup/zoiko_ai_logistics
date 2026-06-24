"""Transparency log over issued ACRs — Merkle-committed, witness-signed.

Revision ID: 0039
Revises: 0038
Create Date: 2026-06-20

Closes the SC-001 acceptance criterion "Transparency log inclusion proof
and witness co-signature verify" — previously nothing existed: no table,
no commit process, no inclusion proof.

LIMITATION (deliberately not hidden): the witness signature in this first
version is produced by the same signing key/process used everywhere else
(shared.signer.sign). A real witness co-signature needs an independent key
custodian; swapping a second signer into TransparencyLogHandler._commit_pending()
is the only change needed once that custodian exists. Building a fake
"independent" signature with the same key would be dishonest, so this is
flagged rather than disguised.

transparency_log_commits — one row per Merkle-tree batch commit:
  - root_hash           BYTEA — Merkle root over all leaf_hashes in this commit
  - leaf_count          INTEGER
  - witness_signature   BYTEA — signature over root_hash
  - witness_kid         TEXT

transparency_log_entries — one row per ACR appended to the log:
  - acr_id      UUID — the ACR this entry proves was logged
  - log_index   BIGINT — sequential position in this tenant's log
  - leaf_hash   BYTEA — domain-tagged hash of (acr_id || acr_merkle_root)
  - commit_id   UUID — NULL until batched into a commit
"""
from alembic import op

revision      = "0039"
down_revision = "0038"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS transparency_log_commits (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id           UUID NOT NULL REFERENCES tenants(id),
            root_hash           BYTEA NOT NULL,
            leaf_count          INTEGER NOT NULL,
            witness_signature   BYTEA NOT NULL,
            witness_kid         TEXT NOT NULL,
            committed_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS transparency_log_entries (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id    UUID NOT NULL REFERENCES tenants(id),
            acr_id       UUID NOT NULL REFERENCES action_certification_records(id),
            log_index    BIGINT NOT NULL,
            leaf_hash    BYTEA NOT NULL,
            commit_id    UUID REFERENCES transparency_log_commits(id),
            appended_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (tenant_id, log_index),
            UNIQUE (tenant_id, acr_id)
        )
    """)

    op.execute("CREATE INDEX IF NOT EXISTS idx_tle_pending ON transparency_log_entries(tenant_id) WHERE commit_id IS NULL")

    for tbl in ("transparency_log_commits", "transparency_log_entries"):
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_tle_pending")
    op.execute("DROP TABLE IF EXISTS transparency_log_entries")
    op.execute("DROP TABLE IF EXISTS transparency_log_commits")
