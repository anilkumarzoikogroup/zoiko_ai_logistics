"""Migration 0011 — SC-005 Accessorial Charge Dispute schema.

Adds:
  - accessorial_tariff_caps  (contracted cap per carrier/charge-type reference)
  - accessorial_charges      (per-invoice multi-line dispute records)

Extends:
  - cases.case_type_check    to include ACCESSORIAL_DISPUTE
  - cases.chk_cases_subject  to allow ACCESSORIAL_DISPUTE rows

Revision ID: 0011_sc005_accessorial_dispute
Revises: 0010_sc004_runtime_schema
Create Date: 2026-06-27
"""
from __future__ import annotations

import os
from alembic import op

revision      = "0011_sc005_accessorial_dispute"
down_revision = "0010_sc004_runtime_schema"
branch_labels = None
depends_on    = None

_HERE     = os.path.dirname(os.path.abspath(__file__))
_SQL_FILE = os.path.join(_HERE, "0011_sc005_accessorial_dispute.sql")


def upgrade() -> None:
    with open(_SQL_FILE, encoding="utf-8") as f:
        op.execute(f.read())


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS accessorial_charges CASCADE")
    op.execute("DROP TABLE IF EXISTS accessorial_tariff_caps CASCADE")
