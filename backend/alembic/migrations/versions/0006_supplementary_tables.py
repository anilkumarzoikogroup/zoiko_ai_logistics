"""Migration 0006 — Supplementary tracking tables for Build Map domains 8–12.

Adds:
  - agent_invocations        (domain 8 — reasoning audit trail)
  - token_revocations        (domain 9 — explicit token revocations)
  - connector_registrations  (domain 10 — certified carrier connectors)
  - connector_dispatches     (domain 10 — per-execution connector call log)
  - aging_buckets            (domain 11 — recovery aging snapshots)
  - transparency_log_entries (domain 12 — co-signed ACR transparency log)
  - claim_policy_caps        (domain 5 — SC-002 claim amount policy caps)

All tables have UUID PK + tenant_id + created_at per DB rules.
RLS enabled on all tables. Append-only tables: agent_invocations,
token_revocations, connector_dispatches, transparency_log_entries.

Revision ID: 0006_supplementary_tables
Revises: 0005_sc003_shipment_events
Create Date: 2026-06-26
"""
from __future__ import annotations

import os
from alembic import op

revision      = "0006_supplementary_tables"
down_revision = "0005_sc003_shipment_events"
branch_labels = None
depends_on    = None

_HERE     = os.path.dirname(os.path.abspath(__file__))
_SQL_FILE = os.path.join(_HERE, "0006_supplementary_tables.sql")


def upgrade() -> None:
    with open(_SQL_FILE, encoding="utf-8") as f:
        op.execute(f.read())


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS claim_policy_caps CASCADE")
    op.execute("DROP TABLE IF EXISTS transparency_log_entries CASCADE")
    op.execute("DROP TABLE IF EXISTS aging_buckets CASCADE")
    op.execute("DROP TABLE IF EXISTS connector_dispatches CASCADE")
    op.execute("DROP TABLE IF EXISTS connector_registrations CASCADE")
    op.execute("DROP TABLE IF EXISTS token_revocations CASCADE")
    op.execute("DROP TABLE IF EXISTS agent_invocations CASCADE")
