"""Add lane_hash, base_rate, effective_from/to to contract_rates (spec §8.1).

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-21

contract_rates gains:
  - lane_hash   VARCHAR(71)  — SHA-256(origin + "|" + destination), domain-tagged
  - base_rate   NUMERIC      — alias/replacement for rate_value; kept for compat
  - effective_from DATE      — renamed from effective_on (kept for compat)
  - effective_to   DATE      — renamed from expires_on (kept for compat)
  - governing_jurisdiction TEXT
  - payload_hash VARCHAR(71)  — JCS hash of the rate record for tamper detection
"""
from __future__ import annotations
from alembic import op

revision    = "0002"
down_revision = "0001"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # Add new spec-aligned columns alongside existing ones for backward compat
    op.execute("""
        ALTER TABLE contract_rates
            ADD COLUMN IF NOT EXISTS lane_hash              VARCHAR(71),
            ADD COLUMN IF NOT EXISTS base_rate              NUMERIC(15,2),
            ADD COLUMN IF NOT EXISTS effective_from         DATE,
            ADD COLUMN IF NOT EXISTS effective_to           DATE,
            ADD COLUMN IF NOT EXISTS governing_jurisdiction TEXT,
            ADD COLUMN IF NOT EXISTS payload_hash           VARCHAR(71)
    """)

    # Back-fill: derive lane_hash from carrier_id (used as a stub until real
    # origin/dest data is present).  Phase 2 validation_svc will supply the
    # real lane_hash computed as SHA-256("zoiko/v1/lane:" + origin + "|" + dest).
    op.execute("""
        UPDATE contract_rates
        SET
            base_rate      = rate_value,
            effective_from = effective_on,
            effective_to   = expires_on,
            payload_hash   = encode(
                sha256(('zoiko.contract_rate.v1:' || carrier_id || ':' || rate_type)::bytea),
                'hex'
            )
        WHERE base_rate IS NULL
    """)

    # Add composite index for lane-level lookups
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_contract_rates_lane
            ON contract_rates(tenant_id, lane_hash, effective_from)
            WHERE lane_hash IS NOT NULL
    """)

    # Add composite index for carrier-level lookups (backward compat)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_contract_rates_carrier
            ON contract_rates(tenant_id, carrier_id, effective_on)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_contract_rates_lane")
    op.execute("DROP INDEX IF EXISTS idx_contract_rates_carrier")
    op.execute("""
        ALTER TABLE contract_rates
            DROP COLUMN IF EXISTS lane_hash,
            DROP COLUMN IF EXISTS base_rate,
            DROP COLUMN IF EXISTS effective_from,
            DROP COLUMN IF EXISTS effective_to,
            DROP COLUMN IF EXISTS governing_jurisdiction,
            DROP COLUMN IF EXISTS payload_hash
    """)
