"""Unified baseline: all shared platform-spine tables (105 tables).

Revision ID: 0001_baseline
Revises: —
Create Date: 2026-06-24

Replaces the old 0001-0040 + the shared portions of 0036/0041 incremental
migrations (43 files total) with one consolidated baseline, squashed against
the live database's actual introspected schema (not re-derived by replaying
the old files, since several of them — 0032-0035 — corrected drift introduced
by earlier ones; the live DB's real structure is the source of truth here).

The genuinely slice-specific pieces (SC-002's `claims`/`claim_lines` tables and
the `cases.claim_id`/`cases.case_type` lift) live in `0002_integration_tables.py`
instead — see `SLICE_MAP.md` for the full reasoning on why most of this baseline
is shared spine, not any one slice's migration, and why the live alembic_version
chain can't be split per-slice.

DDL lives in the adjacent `baseline_schema.sql` (kept as plain SQL so it's
reviewable independent of Python/alembic ceremony — same pattern as Atheera's
`db/alembic/versions/baseline_schema.sql`). This file just reads and executes it.

Validated before being adopted as history: executed standalone against a
throwaway database and diffed table/column/constraint/index counts against the
live DB — exact match (107 tables, 1297 columns, 1370 constraints, 192 indexes
counting both this migration and 0002 together).
"""
from __future__ import annotations

import os

from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

_HERE = os.path.dirname(os.path.abspath(__file__))
_SQL_FILE = os.path.join(_HERE, "baseline_schema.sql")


def upgrade() -> None:
    with open(_SQL_FILE, encoding="utf-8") as f:
        op.execute(f.read())


def downgrade() -> None:
    tables = [
        "action_certification_records", "action_intents", "action_plans",
        "agent_tool_permissions", "ambiguity_queue", "api_keys", "approval_decisions",
        "approval_group_members", "approval_groups", "approval_requests", "approval_tasks",
        "approval_thresholds", "archive_jobs", "assertion_results", "audit_chains",
        "audit_worm_index", "authorization_decisions", "batch_artifacts", "batch_records",
        "business_units", "canonical_invoices", "canonical_shipments", "carriers",
        "case_candidates", "case_events", "case_timeline_entries", "cases",
        "certification_runs", "confidence_assessments", "connector_responses", "connectors",
        "contract_clauses", "contract_rates", "crypto_shred_requests", "decision_proposals",
        "dedup_index", "dispatch_tickets", "documents", "drift_signals", "evaluation_runs",
        "evidence_bundle_leaves", "evidence_bundles", "evidence_items", "execution_envelopes",
        "expected_recoveries", "explanation_artifacts", "external_acknowledgments",
        "external_responses", "facilities", "findings", "governance_decisions",
        "governance_tokens", "idempotency_keys", "ingestion_runs", "invitation_tokens",
        "invoice_lines", "ledger_entries", "legal_hold_records", "lineage_records",
        "model_calls", "outbox", "outcomes", "override_records", "password_reset_otp",
        "password_reset_tokens", "password_reset_verify", "policy_bundles", "policy_packs",
        "proofs_of_delivery", "purge_jobs", "quarantine_items", "reasoning_traces",
        "reconciliations", "recovery_instruments", "recovery_matches", "recovery_proofs",
        "release_gate_scoreboards", "restore_jobs", "restore_verification_records",
        "retention_markers", "retention_policies", "rule_traces", "shipment_legs",
        "shipments", "signup_verification", "source_record_states", "source_records",
        "sso_domains", "step_up_assertions", "submit_jobs", "tasks", "tenant_keys",
        "tenant_notification_settings", "tenants", "threshold_profiles",
        "transparency_log_commits", "transparency_log_entries", "users",
        "validation_results", "validation_rule_sets", "variance_records",
        "webhook_signing_configs", "witness_packs", "workspace_access_requests",
        "write_offs",
    ]
    for tbl in tables:
        op.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE")
