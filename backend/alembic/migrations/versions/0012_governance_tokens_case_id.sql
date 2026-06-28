-- =============================================================================
-- Migration 0012 — Add case_id to governance_tokens
-- =============================================================================
-- SC-003, SC-004, and SC-005 governance handlers write case_id into
-- governance_tokens so that execution-side queries can JOIN tokens directly
-- to cases without a multi-hop join through decisions/tasks.
-- Safe to run multiple times — uses IF NOT EXISTS.
-- =============================================================================

ALTER TABLE governance_tokens ADD COLUMN IF NOT EXISTS case_id UUID REFERENCES cases(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_governance_tokens_case_id
    ON governance_tokens (case_id) WHERE case_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_governance_tokens_tenant_case
    ON governance_tokens (tenant_id, case_id) WHERE case_id IS NOT NULL;

-- =============================================================================
-- END OF MIGRATION 0012
-- =============================================================================
