"""Certification tables — TCP certification runs and assertion results.

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-27

L11, C-10, Sprint 8: Technical Certification Probes (TCP) verify that each
gate in the execution pipeline behaves correctly under controlled conditions.

certification_runs  — one record per certification execution (pass/fail summary)
assertion_results   — one record per individual assertion within a run
release_gate_scoreboards — aggregated gate scores used for release sign-off
"""
from __future__ import annotations
from alembic import op

revision      = "0008"
down_revision = "0007"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ── certification_runs ───────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE certification_runs (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID REFERENCES tenants(id),
        run_type        TEXT NOT NULL CHECK (run_type IN
                            ('TCP','SMOKE','REGRESSION','RELEASE_GATE')),
        target_service  TEXT NOT NULL,
        policy_version  TEXT NOT NULL DEFAULT 'v1.0.0',
        total_assertions INTEGER NOT NULL DEFAULT 0,
        passed          INTEGER NOT NULL DEFAULT 0,
        failed          INTEGER NOT NULL DEFAULT 0,
        skipped         INTEGER NOT NULL DEFAULT 0,
        status          TEXT NOT NULL DEFAULT 'RUNNING'
                          CHECK (status IN ('RUNNING','PASSED','FAILED','ABORTED')),
        started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        completed_at    TIMESTAMPTZ,
        triggered_by    TEXT NOT NULL DEFAULT 'system'
    )""")

    # ── assertion_results ────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE assertion_results (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        run_id          UUID NOT NULL REFERENCES certification_runs(id),
        assertion_name  TEXT NOT NULL,
        gate_number     INTEGER,
        expected        TEXT,
        actual          TEXT,
        passed          BOOLEAN NOT NULL DEFAULT FALSE,
        error_message   TEXT,
        duration_ms     INTEGER,
        asserted_at     TIMESTAMPTZ NOT NULL DEFAULT now()
    )""")

    # ── release_gate_scoreboards ─────────────────────────────────────────────
    op.execute("""
    CREATE TABLE release_gate_scoreboards (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        run_id          UUID NOT NULL REFERENCES certification_runs(id),
        gate_number     INTEGER NOT NULL,
        gate_name       TEXT NOT NULL,
        score           NUMERIC(5,2) NOT NULL DEFAULT 0.0
                          CHECK (score BETWEEN 0 AND 100),
        weight          NUMERIC(5,2) NOT NULL DEFAULT 1.0,
        verdict         TEXT NOT NULL CHECK (verdict IN ('PASS','FAIL','SKIP')),
        recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now()
    )""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS release_gate_scoreboards CASCADE")
    op.execute("DROP TABLE IF EXISTS assertion_results CASCADE")
    op.execute("DROP TABLE IF EXISTS certification_runs CASCADE")
