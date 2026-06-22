"""Add signature/kid columns to evidence_items — they were computed and discarded.

Revision ID: 0038
Revises: 0037
Create Date: 2026-06-20

EvidenceHandler.add_item() (and the duplicate inline copy in the gateway's
_run_evidence_and_reasoning) already computed `signature, kid = sign(...)`
for every evidence item, but evidence_items had no columns to store them —
the per-item signature was silently thrown away after being computed, so
nothing on a single evidence item was independently verifiable; only the
bundle-level signature existed.

evidence_items gains:
  - signature   BYTEA — per-item Ed25519 signature over item_hash
  - kid         TEXT  — signing key id used

Nullable: evidence_items is APPEND-ONLY and historical rows were genuinely
never signed — backfilling a fake signature for old rows would be
cryptographically dishonest. New rows must populate both going forward
(enforced in application code, not a DB constraint, to avoid breaking the
existing append-only insert path with no chance to migrate live writers).
"""
from alembic import op

revision      = "0038"
down_revision = "0037"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE evidence_items
            ADD COLUMN IF NOT EXISTS signature BYTEA,
            ADD COLUMN IF NOT EXISTS kid       TEXT
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE evidence_items
            DROP COLUMN IF EXISTS signature,
            DROP COLUMN IF EXISTS kid
    """)
