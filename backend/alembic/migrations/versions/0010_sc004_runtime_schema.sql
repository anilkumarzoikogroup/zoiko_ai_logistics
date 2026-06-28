-- =============================================================================
-- SC-004 Runtime Schema — Migration 0010
-- =============================================================================
-- Adds missing tables and columns that SC-003/SC-004 handlers write to.
-- Safe to run multiple times — all statements use IF NOT EXISTS / DO NOTHING.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- BLOCK 1: governance_tasks — SC-003 and SC-004 governance handlers write here
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS governance_tasks (
    id                UUID        NOT NULL DEFAULT gen_random_uuid()
                                  CONSTRAINT pk_governance_tasks PRIMARY KEY,
    tenant_id         UUID        NOT NULL,
    case_id           UUID        REFERENCES cases(id) ON DELETE SET NULL,
    task_type         TEXT        NOT NULL,
    status            TEXT        NOT NULL DEFAULT 'PENDING_APPROVAL',
    proposer_sub      TEXT,
    actor_sub         TEXT,
    proposal_payload  JSONB,
    policy_version    TEXT,
    scorecard_id      UUID        REFERENCES scorecard_periods(id) ON DELETE SET NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_governance_tasks_tenant_case
    ON governance_tasks (tenant_id, case_id);
CREATE INDEX IF NOT EXISTS ix_governance_tasks_scorecard_id
    ON governance_tasks (scorecard_id) WHERE scorecard_id IS NOT NULL;


-- -----------------------------------------------------------------------------
-- BLOCK 2: Add finding_id to scorecard_periods (links breach period to finding)
-- -----------------------------------------------------------------------------

ALTER TABLE scorecard_periods ADD COLUMN IF NOT EXISTS finding_id UUID;
CREATE INDEX IF NOT EXISTS ix_scorecard_periods_case_id
    ON scorecard_periods (case_id) WHERE case_id IS NOT NULL;


-- -----------------------------------------------------------------------------
-- BLOCK 3: Extend cases.case_type to include SCORECARD_BREACH
-- -----------------------------------------------------------------------------

DO $$
BEGIN
    ALTER TABLE cases DROP CONSTRAINT IF EXISTS cases_case_type_check;
    ALTER TABLE cases DROP CONSTRAINT IF EXISTS chk_cases_case_type;
    ALTER TABLE cases
        ADD CONSTRAINT cases_case_type_check
        CHECK (case_type = ANY (ARRAY[
            'INVOICE_OVERCHARGE',
            'CARRIER_CLAIM',
            'SHIPMENT_EXCEPTION',
            'SCORECARD_BREACH'
        ]));
EXCEPTION WHEN others THEN NULL;
END;
$$;

DO $$
BEGIN
    ALTER TABLE cases DROP CONSTRAINT IF EXISTS chk_cases_subject;
    ALTER TABLE cases ADD CONSTRAINT chk_cases_subject CHECK (
        ((case_type = 'INVOICE_OVERCHARGE') AND (invoice_id IS NOT NULL) AND (claim_id IS NULL))
        OR
        ((case_type = 'CARRIER_CLAIM')      AND (claim_id IS NOT NULL)  AND (invoice_id IS NULL))
        OR
        ((case_type = 'SHIPMENT_EXCEPTION') AND (invoice_id IS NULL)    AND (claim_id IS NULL))
        OR
        ((case_type = 'SCORECARD_BREACH')   AND (invoice_id IS NULL)    AND (claim_id IS NULL))
    );
EXCEPTION WHEN others THEN NULL;
END;
$$;


-- -----------------------------------------------------------------------------
-- BLOCK 4: execution_envelopes — add columns that SC-003/004 handlers expect
-- -----------------------------------------------------------------------------

ALTER TABLE execution_envelopes ADD COLUMN IF NOT EXISTS action      TEXT;
ALTER TABLE execution_envelopes ADD COLUMN IF NOT EXISTS payload     JSONB;
ALTER TABLE execution_envelopes ADD COLUMN IF NOT EXISTS created_at  TIMESTAMPTZ;


-- -----------------------------------------------------------------------------
-- BLOCK 5: reconciliations — add columns that SC-003/004 handlers expect
-- -----------------------------------------------------------------------------

ALTER TABLE reconciliations ADD COLUMN IF NOT EXISTS strategy    TEXT;
ALTER TABLE reconciliations ADD COLUMN IF NOT EXISTS summary     JSONB;
ALTER TABLE reconciliations ADD COLUMN IF NOT EXISTS status      TEXT;
ALTER TABLE reconciliations ADD COLUMN IF NOT EXISTS actor_sub   TEXT;
ALTER TABLE reconciliations ADD COLUMN IF NOT EXISTS created_at  TIMESTAMPTZ;


-- -----------------------------------------------------------------------------
-- BLOCK 6: outcomes — add columns that SC-003/004 handlers expect
-- -----------------------------------------------------------------------------

ALTER TABLE outcomes ADD COLUMN IF NOT EXISTS reconciliation_id UUID;
ALTER TABLE outcomes ADD COLUMN IF NOT EXISTS details           JSONB;
ALTER TABLE outcomes ADD COLUMN IF NOT EXISTS status            TEXT;
ALTER TABLE outcomes ADD COLUMN IF NOT EXISTS actor_sub         TEXT;
ALTER TABLE outcomes ADD COLUMN IF NOT EXISTS created_at        TIMESTAMPTZ;


-- -----------------------------------------------------------------------------
-- BLOCK 7: reconciliation_variances — create table for SC-003/004 variance rows
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS reconciliation_variances (
    id                   UUID        NOT NULL DEFAULT gen_random_uuid()
                                     CONSTRAINT pk_recon_variances PRIMARY KEY,
    tenant_id            UUID        NOT NULL,
    case_id              UUID        REFERENCES cases(id) ON DELETE SET NULL,
    reconciliation_id    UUID,
    variance_type        TEXT        NOT NULL,
    expected_value       TEXT,
    actual_value         TEXT,
    delta                TEXT,
    status               TEXT        NOT NULL DEFAULT 'OPEN',
    resolution_note      TEXT,
    resolved_by          TEXT,
    resolved_at          TIMESTAMPTZ,
    actor_sub            TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_recon_variances_tenant_case
    ON reconciliation_variances (tenant_id, case_id);


-- -----------------------------------------------------------------------------
-- BLOCK 8: action_certification_records — add columns that handlers expect
-- -----------------------------------------------------------------------------

ALTER TABLE action_certification_records ADD COLUMN IF NOT EXISTS artifact_count INT;
ALTER TABLE action_certification_records ADD COLUMN IF NOT EXISTS issued_by      TEXT;
ALTER TABLE action_certification_records ADD COLUMN IF NOT EXISTS is_locked      BOOLEAN DEFAULT false;
ALTER TABLE action_certification_records ADD COLUMN IF NOT EXISTS issued_at      TIMESTAMPTZ;


-- -----------------------------------------------------------------------------
-- BLOCK 9: audit_worm_index — add columns that handlers expect
-- -----------------------------------------------------------------------------

ALTER TABLE audit_worm_index ADD COLUMN IF NOT EXISTS record_type TEXT;
ALTER TABLE audit_worm_index ADD COLUMN IF NOT EXISTS record_id   UUID;
ALTER TABLE audit_worm_index ADD COLUMN IF NOT EXISTS record_hash TEXT;
ALTER TABLE audit_worm_index ADD COLUMN IF NOT EXISTS locked_at   TIMESTAMPTZ;
ALTER TABLE audit_worm_index ADD COLUMN IF NOT EXISTS locked_by   TEXT;


-- =============================================================================
-- END OF MIGRATION 0010
-- =============================================================================
