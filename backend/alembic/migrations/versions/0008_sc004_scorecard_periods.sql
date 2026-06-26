-- =============================================================================
-- SC-004 Supplier Performance Scorecard — Migration 0008
-- =============================================================================
-- Creates the scorecard_periods table used by ScorecardHandler.compute().
-- Also ensures sc003_shipment_events schema is applied (idempotent).
-- Safe to run multiple times — all statements use IF NOT EXISTS / DO NOTHING.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- BLOCK 1: scorecard_periods — one row per (tenant, carrier, period) scorecard
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS scorecard_periods (
    id                       UUID        NOT NULL DEFAULT gen_random_uuid()
                                         CONSTRAINT pk_scorecard_periods PRIMARY KEY,

    tenant_id                UUID        NOT NULL,

    -- Carrier identifier (text — matches claims.carrier_id)
    carrier_id               TEXT        NOT NULL,

    -- Supplier alias — same as carrier_id for now; reserved for future M:1 mapping
    supplier_id              TEXT,

    -- Evaluation window
    period_start             TIMESTAMPTZ NOT NULL,
    period_end               TIMESTAMPTZ NOT NULL,

    -- Raw KPI metrics (stored for auditability)
    on_time_rate             NUMERIC(6,4)  NOT NULL DEFAULT 1.0,
    damage_rate              NUMERIC(6,4)  NOT NULL DEFAULT 0.0,
    claim_frequency          NUMERIC(10,2) NOT NULL DEFAULT 0.0,
    dispute_turnaround_days  NUMERIC(8,2)  NOT NULL DEFAULT 0.0,

    -- Composite score (0–100) and threshold
    composite_score          NUMERIC(6,2)  NOT NULL DEFAULT 100.0,
    contracted_threshold     NUMERIC(6,2)  NOT NULL DEFAULT 70.0,

    -- Breach flag + amount
    breach_detected          BOOLEAN       NOT NULL DEFAULT false,
    breach_amount            NUMERIC(18,4) NOT NULL DEFAULT 0.0,

    -- Currency for breach_amount
    currency                 TEXT          NOT NULL DEFAULT 'INR',

    -- Cryptographic record hash (SHA-256 tagged with "zoiko.scorecard.v1:")
    record_hash              BYTEA,

    computed_at              TIMESTAMPTZ,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE scorecard_periods IS
    'SC-004 supplier scorecard — one row per (tenant, carrier, evaluation period). '
    'Composite score = 0.40×on_time + 0.30×quality + 0.20×frequency + 0.10×resolution.';

-- Backfill: add computed_at if table was created before this column existed
ALTER TABLE scorecard_periods ADD COLUMN IF NOT EXISTS computed_at TIMESTAMPTZ;

-- Safety net: canonical_shipment_exceptions is created inline by SC-003 canonical_truth handler
-- on first run. Create it here so SC-004 scorecard queries never fail on a fresh DB.
CREATE TABLE IF NOT EXISTS canonical_shipment_exceptions (
    id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            UUID        NOT NULL,
    source_record_id     UUID        NOT NULL,
    case_id              UUID,
    shipment_reference   TEXT        NOT NULL,
    carrier_id           TEXT        NOT NULL,
    committed_eta        TIMESTAMPTZ NOT NULL,
    actual_delivery      TIMESTAMPTZ NOT NULL,
    sla_breach_hours     FLOAT       NOT NULL DEFAULT 0,
    sla_penalty_amount   FLOAT       NOT NULL DEFAULT 0,
    currency             TEXT        NOT NULL DEFAULT 'INR',
    origin               TEXT,
    destination          TEXT,
    canonical_hash       BYTEA       NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_canonical_shipment_ref UNIQUE (tenant_id, shipment_reference)
);


-- -----------------------------------------------------------------------------
-- BLOCK 2: Indexes on scorecard_periods
-- -----------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS ix_scorecard_periods_tenant_carrier
    ON scorecard_periods (tenant_id, carrier_id);

CREATE INDEX IF NOT EXISTS ix_scorecard_periods_created_at
    ON scorecard_periods (tenant_id, created_at DESC);


-- -----------------------------------------------------------------------------
-- BLOCK 3: SC-003 safety net — ensure cases columns and shipment_events exist.
-- These are idempotent (IF NOT EXISTS / DROP ... IF EXISTS).
-- If sc003_shipment_events.sql was already applied this is a no-op.
-- -----------------------------------------------------------------------------

ALTER TABLE cases ADD COLUMN IF NOT EXISTS shipment_reference  TEXT;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS committed_eta       TIMESTAMPTZ;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS actual_delivery     TIMESTAMPTZ;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS sla_breach_hours    NUMERIC(10,4);
ALTER TABLE cases ADD COLUMN IF NOT EXISTS sla_penalty_amount  NUMERIC(18,4);

-- Extend case_type CHECK constraint to include SHIPMENT_EXCEPTION
DO $$
BEGIN
    ALTER TABLE cases DROP CONSTRAINT IF EXISTS cases_case_type_check;
    ALTER TABLE cases DROP CONSTRAINT IF EXISTS chk_cases_case_type;
    ALTER TABLE cases
        ADD CONSTRAINT cases_case_type_check
        CHECK (case_type = ANY (ARRAY[
            'INVOICE_OVERCHARGE',
            'CARRIER_CLAIM',
            'SHIPMENT_EXCEPTION'
        ]));
EXCEPTION WHEN others THEN NULL;
END;
$$;

-- Extend chk_cases_subject to allow SHIPMENT_EXCEPTION (no invoice_id or claim_id)
DO $$
BEGIN
    ALTER TABLE cases DROP CONSTRAINT IF EXISTS chk_cases_subject;
    ALTER TABLE cases ADD CONSTRAINT chk_cases_subject CHECK (
        ((case_type = 'INVOICE_OVERCHARGE') AND (invoice_id IS NOT NULL) AND (claim_id IS NULL))
        OR
        ((case_type = 'CARRIER_CLAIM')      AND (claim_id IS NOT NULL)  AND (invoice_id IS NULL))
        OR
        ((case_type = 'SHIPMENT_EXCEPTION') AND (invoice_id IS NULL)    AND (claim_id IS NULL))
    );
EXCEPTION WHEN others THEN NULL;
END;
$$;

CREATE TABLE IF NOT EXISTS shipment_events (
    id                  UUID        NOT NULL DEFAULT gen_random_uuid()
                                    CONSTRAINT pk_shipment_events PRIMARY KEY,
    tenant_id           UUID        NOT NULL,
    case_id             UUID        REFERENCES cases(id) ON DELETE SET NULL,
    source_record_id    UUID,
    shipment_reference  TEXT        NOT NULL DEFAULT '',
    event_type          TEXT        NOT NULL,
    occurred_at         TIMESTAMPTZ NOT NULL,
    location            TEXT,
    carrier_id          TEXT        NOT NULL DEFAULT '',
    raw_payload         JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_shipment_events_tenant_case
    ON shipment_events (tenant_id, case_id);

CREATE INDEX IF NOT EXISTS ix_shipment_events_shipment_ref
    ON shipment_events (shipment_reference);

CREATE UNIQUE INDEX IF NOT EXISTS uq_cases_tenant_shipment
    ON cases (tenant_id, shipment_reference)
    WHERE sla_breach_hours IS NOT NULL;


-- =============================================================================
-- END OF MIGRATION 0008
-- =============================================================================
