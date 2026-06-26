"""Migration 0007 — Canonical Logistics Truth (Domain 4) +
Commercial Reference Data (Domain 5) + Transparency log enrichment (Domain 12).

Adds:
  Domain 4 — Canonical Logistics Truth (missing from baseline):
    - stops               (route waypoints)
    - suppliers           (vendor master)
    - warehouses          (physical storage locations)
    - equipment_types     (truck/container/pallet types)
    - service_levels      (SLA tier definitions per carrier)
    - purchase_orders     (procurement PO headers)
    - accessorials        (surcharge line items on shipments)
    - disputes            (formal dispute records)
    - inventory_movements (warehouse stock events)

  Domain 5 — Commercial Reference Data (missing from baseline):
    - master_service_agreements  (carrier MSA headers)
    - carrier_agreements         (per-lane agreements under an MSA)
    - lanes                      (origin-destination pairs)
    - lane_bundles + lane_bundle_members
    - rate_schedules             (versioned tariff headers)
    - charge_components          (line items within a rate schedule)
    - charge_tiers               (volume/weight break points)
    - contract_rate_versions     (audit history for contract_rates rows)
    - accessorial_tariffs        (carrier-published accessorial schedules)
    - spot_quotes                (one-off price quotes outside contract rates)

  Domain 12 — Transparency log enrichment:
    - ALTER TABLE transparency_log_entries ADD COLUMN IF NOT EXISTS
      (case_id, entry_type, entry_hash, prev_entry_hash, payload,
       signature, kid, co_signature, co_kid, co_signed_at, co_signed_by,
       is_locked, logged_at, created_at)

All tables: UUID PK + tenant_id + created_at. RLS enabled.
Append-only tables: stops, accessorials, inventory_movements.

Revision ID: 0007_canonical_commercial_tables
Revises: 0006_supplementary_tables
Create Date: 2026-06-26
"""
from __future__ import annotations

import os
from alembic import op

revision      = "0007_canonical_commercial_tables"
down_revision = "0006_supplementary_tables"
branch_labels = None
depends_on    = None

_HERE     = os.path.dirname(os.path.abspath(__file__))
_SQL_FILE = os.path.join(_HERE, "0007_canonical_commercial_tables.sql")


def upgrade() -> None:
    with open(_SQL_FILE, encoding="utf-8") as f:
        op.execute(f.read())


def downgrade() -> None:
    # Drop in reverse dependency order
    for table in [
        "spot_quotes",
        "accessorial_tariffs",
        "contract_rate_versions",
        "charge_tiers",
        "charge_components",
        "rate_schedules",
        "lane_bundle_members",
        "lane_bundles",
        "lanes",
        "carrier_agreements",
        "master_service_agreements",
        "inventory_movements",
        "disputes",
        "accessorials",
        "purchase_orders",
        "service_levels",
        "equipment_types",
        "warehouses",
        "suppliers",
        "stops",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    # Remove added columns from transparency_log_entries (best-effort)
    for col in [
        "case_id", "entry_type", "entry_hash", "prev_entry_hash",
        "payload", "signature", "kid", "co_signature", "co_kid",
        "co_signed_at", "co_signed_by", "is_locked", "logged_at", "created_at",
    ]:
        op.execute(
            f"ALTER TABLE transparency_log_entries DROP COLUMN IF EXISTS {col}"
        )
