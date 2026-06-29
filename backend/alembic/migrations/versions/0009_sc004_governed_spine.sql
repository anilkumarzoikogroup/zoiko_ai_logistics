-- =============================================================================
-- SC-004 Governed Spine — Migration 0009
-- =============================================================================
-- Extends scorecard_periods with case linkage so breach scorecard rows can
-- participate in the full governed execution chain (case→evidence→finding→
-- governance→token→execution→reconciliation→ACR).
--
-- Also extends the cases table to support SCORECARD_BREACH case type.
-- Safe to run multiple times — all statements use IF NOT EXISTS / DO NOTHING.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- BLOCK 1: Link scorecard_periods to a governed case on breach
-- -----------------------------------------------------------------------------

ALTER TABLE scorecard_periods ADD COLUMN IF NOT EXISTS case_id UUID REFERENCES cases(id) ON DELETE SET NULL;
ALTER TABLE scorecard_periods ADD COLUMN IF NOT EXISTS finding_id UUID;

CREATE INDEX IF NOT EXISTS ix_scorecard_periods_case_id ON scorecard_periods (case_id) WHERE case_id IS NOT NULL;


-- -----------------------------------------------------------------------------
-- BLOCK 2: Extend cases.case_type to include SCORECARD_BREACH
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

-- Allow SCORECARD_BREACH cases to have neither invoice_id nor claim_id
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


-- scorecard_id column on governance_tasks is added by migration 0010
-- (governance_tasks is created in 0010, so ALTER must happen after CREATE)

-- =============================================================================
-- END OF MIGRATION 0009
-- =============================================================================
