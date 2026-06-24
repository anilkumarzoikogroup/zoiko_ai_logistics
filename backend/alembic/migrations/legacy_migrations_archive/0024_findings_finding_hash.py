"""Add findings.finding_hash — the SHA-256 domain-tagged hash that is signed.

Revision ID: 0024
Revises: 0023
Create Date: 2026-06-11

The findings table stored only the Ed25519 `signature` over the finding hash,
not the hash itself. ACR generation needs the actual SHA-256 hash
(zoiko.finding.v1: domain tag) as one of its 8 Merkle-tree artifacts —
the signature (64 bytes) was being used in its place (32 bytes expected).
"""
from __future__ import annotations
from alembic import op

revision      = "0024"
down_revision = "0023"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE findings
            ADD COLUMN IF NOT EXISTS finding_hash BYTEA
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE findings
            DROP COLUMN IF EXISTS finding_hash
    """)
