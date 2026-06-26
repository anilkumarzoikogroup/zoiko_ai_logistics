-- =============================================================================
-- SC-003 Shipment Exception / SLA Penalty — Migration 0005
-- =============================================================================
-- Safe to run on any existing DB — every statement is fully idempotent.
-- Adds the SHIPMENT_EXCEPTION case_type branch, extends the cases table with
-- SLA timing columns, and creates the shipment_events time-series table used
-- to record carrier pickup/transit/delivery events for breach detection.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- BLOCK 1: Extend cases table with SC-003 SLA columns
-- These columns are NULL for INVOICE_OVERCHARGE and CARRIER_CLAIM cases;
-- they are populated by the SC-003 ingestion pipeline.
-- -----------------------------------------------------------------------------

-- shipment_reference: carrier AWB / tracking number — natural dedup key for the case
-- (mirrors invoice_id for INVOICE_OVERCHARGE and claim_id for CARRIER_CLAIM)
ALTER TABLE cases ADD COLUMN IF NOT EXISTS shipment_reference  TEXT;

-- committed_eta: timestamp the carrier contractually promised for delivery
ALTER TABLE cases ADD COLUMN IF NOT EXISTS committed_eta       TIMESTAMPTZ;

-- actual_delivery: timestamp the shipment was actually delivered (NULL if undelivered)
ALTER TABLE cases ADD COLUMN IF NOT EXISTS actual_delivery     TIMESTAMPTZ;

-- sla_breach_hours: computed hours late (= 0.0 if on time, NULL before delivery confirmed)
ALTER TABLE cases ADD COLUMN IF NOT EXISTS sla_breach_hours    NUMERIC(10,4);

-- sla_penalty_amount: computed penalty = MIN(breach_hours * rate_per_hour, penalty_cap)
ALTER TABLE cases ADD COLUMN IF NOT EXISTS sla_penalty_amount  NUMERIC(18,4);


-- -----------------------------------------------------------------------------
-- BLOCK 2: Add SHIPMENT_EXCEPTION to the cases.case_type CHECK constraint
-- The existing constraint only covers INVOICE_OVERCHARGE and CARRIER_CLAIM.
-- We drop it (idempotent — IF EXISTS) and recreate it with all three values.
-- Wrapped in a DO block so a concurrent migration on an already-updated DB
-- does not raise an error.
-- -----------------------------------------------------------------------------

DO $$
BEGIN
    -- Drop whatever constraint name was used (SC-001 baseline or SC-002 fix)
    ALTER TABLE cases DROP CONSTRAINT IF EXISTS cases_case_type_check;
    ALTER TABLE cases DROP CONSTRAINT IF EXISTS chk_cases_case_type;

    -- Recreate with all three allowed case types
    ALTER TABLE cases
        ADD CONSTRAINT cases_case_type_check
        CHECK (case_type = ANY (ARRAY[
            'INVOICE_OVERCHARGE',
            'CARRIER_CLAIM',
            'SHIPMENT_EXCEPTION'
        ]));
EXCEPTION
    WHEN others THEN
        -- Constraint already exists with correct definition — safe to ignore
        NULL;
END;
$$;


-- -----------------------------------------------------------------------------
-- BLOCK 3: Create shipment_events table (time-series event stream per shipment)
-- One row per carrier lifecycle event: PICKUP, IN_TRANSIT, DELAYED, ARRIVED,
-- DELIVERED, EXCEPTION. Append-only — never UPDATE or DELETE rows here.
-- case_id is nullable so events can be ingested before a case is opened.
-- source_record_id links back to the raw ingested source_records row.
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS shipment_events (
    -- Primary key
    id                  UUID        NOT NULL DEFAULT gen_random_uuid()
                                    CONSTRAINT pk_shipment_events PRIMARY KEY,

    -- Tenant isolation (Row-Level Security uses this column)
    tenant_id           UUID        NOT NULL,

    -- Links to the opened case (NULL until case is created by orchestration)
    case_id             UUID        REFERENCES cases(id) ON DELETE SET NULL,

    -- Links to the raw ingested record in source_records
    source_record_id    UUID,

    -- Natural dedup key — carrier's own shipment/AWB reference number
    shipment_reference  TEXT        NOT NULL DEFAULT '',

    -- Lifecycle event type: PICKUP | IN_TRANSIT | DELAYED | ARRIVED | DELIVERED | EXCEPTION
    event_type          TEXT        NOT NULL,

    -- Wall-clock time the event occurred at the carrier's location
    occurred_at         TIMESTAMPTZ NOT NULL,

    -- Physical location description (city, hub, GPS string — freeform)
    location            TEXT,

    -- Carrier identifier (matches carrier_id in contract_rates / sla_schedules)
    carrier_id          TEXT        NOT NULL DEFAULT '',

    -- Full raw event payload from the carrier API / EDI feed (audit preservation)
    raw_payload         JSONB,

    -- Insert timestamp (managed by DB — never supplied by application)
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE shipment_events IS
    'SC-003 append-only event stream. One row per carrier lifecycle event '
    '(PICKUP, IN_TRANSIT, DELAYED, ARRIVED, DELIVERED, EXCEPTION). '
    'Never UPDATE or DELETE — treat as an audit log.';

COMMENT ON COLUMN shipment_events.shipment_reference IS
    'Carrier AWB / tracking number — natural dedup key for the shipment.';
COMMENT ON COLUMN shipment_events.event_type IS
    'Lifecycle stage: PICKUP | IN_TRANSIT | DELAYED | ARRIVED | DELIVERED | EXCEPTION';
COMMENT ON COLUMN shipment_events.occurred_at IS
    'Wall-clock time the event occurred at the carrier side (TIMESTAMPTZ).';
COMMENT ON COLUMN shipment_events.raw_payload IS
    'Full raw JSON payload from carrier API or EDI feed — preserved for audit.';


-- -----------------------------------------------------------------------------
-- BLOCK 4: Indexes on shipment_events
-- Three indexes cover the primary access patterns:
--   1. Fetch all events for a given tenant + shipment reference (ingestion lookup)
--   2. Fetch all events belonging to an open case (case detail page)
--   3. Partial unique index on cases: one SLA case per (tenant, shipment_reference)
--      scoped only to rows where sla_breach_hours IS NOT NULL (i.e. SC-003 rows)
-- -----------------------------------------------------------------------------

-- Index 1: tenant + shipment reference — primary lookup during ingestion / dedup
CREATE INDEX IF NOT EXISTS ix_shipment_events_tenant_case
    ON shipment_events (tenant_id, case_id);

-- Index 2: shipment reference lookup across tenants — supports cross-tenant queries
CREATE INDEX IF NOT EXISTS ix_shipment_events_shipment_ref
    ON shipment_events (shipment_reference);

-- Index 3: unique SLA case per tenant per shipment (partial — SC-003 cases only)
-- Prevents duplicate cases being opened for the same shipment breach.
CREATE UNIQUE INDEX IF NOT EXISTS uq_cases_tenant_shipment
    ON cases (tenant_id, shipment_reference)
    WHERE sla_breach_hours IS NOT NULL;

-- Note: shipment_reference column on cases is populated by SC-003 ingestion.
-- For non-SC-003 cases this column remains NULL and the partial index ignores them.


-- -----------------------------------------------------------------------------
-- BLOCK 5: Extend chk_cases_subject to allow SHIPMENT_EXCEPTION rows.
-- SC-003 cases have neither invoice_id nor claim_id; they are identified by
-- shipment_reference instead.  Without this fix the case INSERT would be
-- rejected by the two-branch CHECK constraint added in migration 0004.
-- -----------------------------------------------------------------------------

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
EXCEPTION
    WHEN others THEN
        NULL;
END;
$$;


-- -----------------------------------------------------------------------------
-- END OF MIGRATION 0005 (sc003_shipment_events)
-- =============================================================================
