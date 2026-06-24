"""SC-002 (Carrier Claim) integration: lifts `cases` to carry a claim as well as
an invoice, and adds the claim-specific tables.

Revision ID: 0002_sc002_integration
Revises: 0001_baseline
Create Date: 2026-06-24

Replaces the slice-specific portions of the old 0019/0041/0042/0043 migrations.
Genuinely the only schema SC-002 owns — see `SLICE_MAP.md` and
`backend/slices/sc-002-carrier-claim/SCHEMA.md` for the full breakdown:
  - `cases.invoice_id` made nullable, `+claim_id`, `+case_type` discriminator,
    `chk_cases_subject` check constraint
  - `claims` table (source_record_id, carrier_id, claim_hash, claim_reference,
    status lifecycle check)
  - `claim_lines` table (multi-line claim breakdown)

DDL lives in the adjacent `integration_schema.sql` — same pattern as `0001`.
"""
from __future__ import annotations

import os

from alembic import op

revision = "0002_sc002_integration"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

_HERE = os.path.dirname(os.path.abspath(__file__))
_SQL_FILE = os.path.join(_HERE, "integration_schema.sql")


def upgrade() -> None:
    with open(_SQL_FILE, encoding="utf-8") as f:
        op.execute(f.read())


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS claim_lines CASCADE")
    op.execute("DROP TABLE IF EXISTS claims CASCADE")
    op.execute("ALTER TABLE cases DROP CONSTRAINT IF EXISTS chk_cases_subject")
    op.execute("ALTER TABLE cases DROP CONSTRAINT IF EXISTS cases_case_type_check")
    op.execute("ALTER TABLE cases DROP COLUMN IF EXISTS case_type")
    op.execute("ALTER TABLE cases DROP COLUMN IF EXISTS claim_id")
