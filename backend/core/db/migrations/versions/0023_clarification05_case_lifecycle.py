"""Clarification 05 — Case Lifecycle, Decision Execution, Recovery Workflow, ACR closure.

Revision ID: 0023
Revises: 0022
Create Date: 2026-06-10

New tables:
  - case_candidates          — finding grouping/promotion before a case is opened
  - action_plans             — recommended action + expected outcome before execution
  - authorization_decisions  — formal policy decision per action plan (Clarification 02)
  - external_responses       — carrier/partner responses re-entering through ingestion
  - evidence_bundle_leaves   — append-only, hash-bound, versioned leaves per lifecycle stage

Extended tables (additive only — no drops/renames):
  - cases                    — closure sub-states, ESCALATED/QUARANTINED/CANDIDATE/
                                RECONCILING + closure_reason
  - findings                 — finding_type, severity, source/canonical record id arrays,
                                rule_set_version, recommended_action
  - execution_envelopes      — idempotency_key, request/response payload hashes,
                                action_plan_id
  - reconciliations          — reconciliation_type, expected/observed amounts
  - action_certification_records — recovered_amount, closure_reason, supersession links
"""
from __future__ import annotations
from alembic import op

revision      = "0023"
down_revision = "0022"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # cases — extend state machine (additive) + closure_reason            #
    # ------------------------------------------------------------------ #
    op.execute("ALTER TABLE cases DROP CONSTRAINT IF EXISTS cases_state_check")
    op.execute("""
        ALTER TABLE cases
            ADD CONSTRAINT cases_state_check
            CHECK (state IN (
                'NEW','EVIDENCE_PENDING','FINDING_GENERATED','APPROVAL_PENDING',
                'EXECUTION_READY','DISPATCHED','OUTCOME_RECORDED','CLOSED','ABORTED',
                'CANDIDATE','UNDER_REVIEW','ACTION_PLAN_READY','READY_FOR_AUTHORIZATION',
                'AUTHORIZED','EXECUTING','AWAITING_EXTERNAL_RESPONSE','RECONCILING',
                'CLOSED_RECOVERED','CLOSED_NO_ACTION','CLOSED_REJECTED','CLOSED_WITHDRAWN',
                'CLOSED_UNRECOVERABLE','CLOSED_DUPLICATE','ESCALATED','QUARANTINED'
            ))
    """)
    op.execute("""
        ALTER TABLE cases
            ADD COLUMN IF NOT EXISTS closure_reason TEXT
                CHECK (closure_reason IS NULL OR closure_reason IN (
                    'RECOVERED_FULL','RECOVERED_PARTIAL','NO_ACTION_REQUIRED',
                    'FINDING_INVALID','DUPLICATE_CASE','UNRECOVERABLE',
                    'WITHDRAWN','EXTERNAL_REJECTED','POLICY_CLOSED'
                )),
            ADD COLUMN IF NOT EXISTS primary_case_id UUID REFERENCES cases(id)
    """)

    # ------------------------------------------------------------------ #
    # findings — Clarification 05 §5 fields                                #
    # ------------------------------------------------------------------ #
    op.execute("""
        ALTER TABLE findings
            ADD COLUMN IF NOT EXISTS finding_type         TEXT,
            ADD COLUMN IF NOT EXISTS severity             TEXT,
            ADD COLUMN IF NOT EXISTS source_record_ids    JSONB NOT NULL DEFAULT '[]',
            ADD COLUMN IF NOT EXISTS canonical_record_ids JSONB NOT NULL DEFAULT '[]',
            ADD COLUMN IF NOT EXISTS rule_set_version     TEXT,
            ADD COLUMN IF NOT EXISTS recommended_action   TEXT,
            ADD COLUMN IF NOT EXISTS superseded_by        UUID REFERENCES findings(id)
    """)

    # ------------------------------------------------------------------ #
    # case_candidates — §6                                                 #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE IF NOT EXISTS case_candidates (
        id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id             UUID NOT NULL REFERENCES tenants(id),
        candidate_type        TEXT NOT NULL,
        finding_ids           JSONB NOT NULL DEFAULT '[]',
        grouping_key          TEXT NOT NULL,
        aggregate_amount      NUMERIC(18,4),
        currency              TEXT NOT NULL DEFAULT 'USD',
        recommended_case_type TEXT NOT NULL,
        recommended_priority  TEXT NOT NULL DEFAULT 'medium',
        promotion_policy_id   TEXT,
        status                TEXT NOT NULL DEFAULT 'PENDING'
                                CHECK (status IN ('PENDING','PROMOTED','REJECTED')),
        promoted_case_id      UUID REFERENCES cases(id),
        rejection_reason      TEXT,
        decided_at            TIMESTAMPTZ,
        created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (tenant_id, grouping_key)
    )""")
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_case_candidates_tenant_status
        ON case_candidates (tenant_id, status)
    """)

    # ------------------------------------------------------------------ #
    # action_plans — §9                                                    #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE IF NOT EXISTS action_plans (
        id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id                UUID NOT NULL REFERENCES tenants(id),
        case_id                  UUID NOT NULL REFERENCES cases(id),
        recommended_action       TEXT NOT NULL,
        expected_outcome         TEXT NOT NULL,
        claimed_amount           NUMERIC(18,4),
        currency                 TEXT NOT NULL DEFAULT 'USD',
        evidence_bundle_id       UUID REFERENCES evidence_bundles(id),
        risk_level               TEXT NOT NULL DEFAULT 'medium',
        authorization_required   BOOLEAN NOT NULL DEFAULT true,
        required_approval_policy_id TEXT,
        created_by               TEXT NOT NULL,
        created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_action_plans_case
        ON action_plans (case_id)
    """)

    # ------------------------------------------------------------------ #
    # authorization_decisions — §11                                        #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE IF NOT EXISTS authorization_decisions (
        id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id           UUID NOT NULL REFERENCES tenants(id),
        case_id             UUID NOT NULL REFERENCES cases(id),
        action_plan_id      UUID NOT NULL REFERENCES action_plans(id),
        action_type         TEXT NOT NULL,
        decision            TEXT NOT NULL CHECK (decision IN ('ALLOW','DENY','ESCALATE')),
        policy_version_id   TEXT NOT NULL,
        required_approvals  JSONB NOT NULL DEFAULT '[]',
        expires_at          TIMESTAMPTZ NOT NULL,
        decided_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        decided_by          TEXT NOT NULL,
        evidence_id         UUID REFERENCES evidence_items(id)
    )""")
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_authz_decisions_action_plan
        ON authorization_decisions (action_plan_id)
    """)

    # ------------------------------------------------------------------ #
    # external_responses — §13                                             #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE IF NOT EXISTS external_responses (
        id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id             UUID NOT NULL REFERENCES tenants(id),
        case_id               UUID NOT NULL REFERENCES cases(id),
        execution_attempt_id  UUID REFERENCES execution_envelopes(id),
        source_record_id      UUID REFERENCES source_records(id),
        response_type         TEXT NOT NULL,
        payload_hash          BYTEA NOT NULL,
        status                TEXT NOT NULL DEFAULT 'RECEIVED'
                                CHECK (status IN ('RECEIVED','LINKED','REQUIRES_REVIEW')),
        received_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_external_responses_case
        ON external_responses (case_id)
    """)

    # ------------------------------------------------------------------ #
    # evidence_bundle_leaves — §10 (versioned, append-only)                #
    # ------------------------------------------------------------------ #
    op.execute("""
        ALTER TABLE evidence_bundles
            ADD COLUMN IF NOT EXISTS bundle_version INTEGER NOT NULL DEFAULT 1
    """)
    op.execute("""
    CREATE TABLE IF NOT EXISTS evidence_bundle_leaves (
        -- APPEND-ONLY: no UPDATE or DELETE ever
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL REFERENCES tenants(id),
        bundle_id       UUID NOT NULL REFERENCES evidence_bundles(id),
        bundle_version  INTEGER NOT NULL,
        leaf_type       TEXT NOT NULL CHECK (leaf_type IN (
                            'source_record','canonical_record','validation_result',
                            'finding','action_plan','authorization','execution',
                            'external_response','reconciliation','closure'
                        )),
        entity_id       UUID NOT NULL,
        leaf_hash       BYTEA NOT NULL,
        added_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_evidence_bundle_leaves_bundle
        ON evidence_bundle_leaves (bundle_id, bundle_version)
    """)

    # ------------------------------------------------------------------ #
    # execution_envelopes — §12 idempotency + request/response hashes     #
    # ------------------------------------------------------------------ #
    op.execute("""
        ALTER TABLE execution_envelopes
            ADD COLUMN IF NOT EXISTS action_plan_id        UUID REFERENCES action_plans(id),
            ADD COLUMN IF NOT EXISTS idempotency_key       TEXT,
            ADD COLUMN IF NOT EXISTS request_payload_hash  BYTEA,
            ADD COLUMN IF NOT EXISTS response_payload_hash BYTEA
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_execution_envelopes_idem
        ON execution_envelopes (tenant_id, idempotency_key)
        WHERE idempotency_key IS NOT NULL
    """)

    # ------------------------------------------------------------------ #
    # reconciliations — §14 reconciliation_type + expected/observed       #
    # ------------------------------------------------------------------ #
    op.execute("""
        ALTER TABLE reconciliations
            ADD COLUMN IF NOT EXISTS reconciliation_type TEXT
                CHECK (reconciliation_type IS NULL OR reconciliation_type IN (
                    'MATCHED','PARTIAL_MATCH','MISMATCH'
                )),
            ADD COLUMN IF NOT EXISTS expected_amount      NUMERIC(18,4),
            ADD COLUMN IF NOT EXISTS observed_amount      NUMERIC(18,4),
            ADD COLUMN IF NOT EXISTS external_response_id UUID REFERENCES external_responses(id)
    """)

    # ------------------------------------------------------------------ #
    # action_certification_records — §16 recovered_amount + supersession  #
    # ------------------------------------------------------------------ #
    op.execute("""
        ALTER TABLE action_certification_records
            ADD COLUMN IF NOT EXISTS closure_reason     TEXT,
            ADD COLUMN IF NOT EXISTS recovered_amount   NUMERIC(18,4),
            ADD COLUMN IF NOT EXISTS currency           TEXT NOT NULL DEFAULT 'USD',
            ADD COLUMN IF NOT EXISTS supersedes_acr_id  UUID REFERENCES action_certification_records(id),
            ADD COLUMN IF NOT EXISTS superseded_by_acr_id UUID REFERENCES action_certification_records(id)
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE action_certification_records
            DROP COLUMN IF EXISTS closure_reason,
            DROP COLUMN IF EXISTS recovered_amount,
            DROP COLUMN IF EXISTS currency,
            DROP COLUMN IF EXISTS supersedes_acr_id,
            DROP COLUMN IF EXISTS superseded_by_acr_id
    """)
    op.execute("""
        ALTER TABLE reconciliations
            DROP COLUMN IF EXISTS reconciliation_type,
            DROP COLUMN IF EXISTS expected_amount,
            DROP COLUMN IF EXISTS observed_amount,
            DROP COLUMN IF EXISTS external_response_id
    """)
    op.execute("DROP INDEX IF EXISTS uq_execution_envelopes_idem")
    op.execute("""
        ALTER TABLE execution_envelopes
            DROP COLUMN IF EXISTS action_plan_id,
            DROP COLUMN IF EXISTS idempotency_key,
            DROP COLUMN IF EXISTS request_payload_hash,
            DROP COLUMN IF EXISTS response_payload_hash
    """)
    op.execute("DROP TABLE IF EXISTS evidence_bundle_leaves")
    op.execute("ALTER TABLE evidence_bundles DROP COLUMN IF EXISTS bundle_version")
    op.execute("DROP TABLE IF EXISTS external_responses")
    op.execute("DROP TABLE IF EXISTS authorization_decisions")
    op.execute("DROP TABLE IF EXISTS action_plans")
    op.execute("DROP TABLE IF EXISTS case_candidates")
    op.execute("""
        ALTER TABLE findings
            DROP COLUMN IF EXISTS finding_type,
            DROP COLUMN IF EXISTS severity,
            DROP COLUMN IF EXISTS source_record_ids,
            DROP COLUMN IF EXISTS canonical_record_ids,
            DROP COLUMN IF EXISTS rule_set_version,
            DROP COLUMN IF EXISTS recommended_action,
            DROP COLUMN IF EXISTS superseded_by
    """)
    op.execute("""
        ALTER TABLE cases
            DROP COLUMN IF EXISTS closure_reason,
            DROP COLUMN IF EXISTS primary_case_id
    """)
    op.execute("ALTER TABLE cases DROP CONSTRAINT IF EXISTS cases_state_check")
    op.execute("""
        ALTER TABLE cases
            ADD CONSTRAINT cases_state_check
            CHECK (state IN (
                'NEW','EVIDENCE_PENDING','FINDING_GENERATED','APPROVAL_PENDING',
                'EXECUTION_READY','DISPATCHED','OUTCOME_RECORDED','CLOSED','ABORTED'
            ))
    """)
