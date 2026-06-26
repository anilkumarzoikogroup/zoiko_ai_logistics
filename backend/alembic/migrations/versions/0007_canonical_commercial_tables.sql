-- =============================================================================
-- Migration 0007 — Canonical Logistics Truth (Domain 4) +
--                  Commercial Reference Data (Domain 5) +
--                  Transparency log column enrichment (Domain 12)
-- =============================================================================
-- Safe to run on any existing DB — all statements are idempotent.
-- Tables that already exist are left untouched (CREATE TABLE IF NOT EXISTS).
-- Columns that already exist are skipped (ADD COLUMN IF NOT EXISTS).
-- =============================================================================


-- =============================================================================
-- BLOCK A: Enrich transparency_log_entries (Domain 12)
-- The baseline created a minimal leaf-hash table. Promote it to a fully
-- co-signed, hash-chained transparency log for ACR events.
-- =============================================================================

ALTER TABLE transparency_log_entries ADD COLUMN IF NOT EXISTS case_id      UUID REFERENCES cases(id);
ALTER TABLE transparency_log_entries ADD COLUMN IF NOT EXISTS entry_type   TEXT
    CHECK (entry_type IN ('ACR_ISSUED','TOKEN_ISSUED','TOKEN_CONSUMED',
                          'EXECUTION_DISPATCHED','RECOVERY_CLOSED',
                          'KEY_ROTATION','AUDIT_CHECKPOINT'));
ALTER TABLE transparency_log_entries ADD COLUMN IF NOT EXISTS entry_hash   BYTEA;
ALTER TABLE transparency_log_entries ADD COLUMN IF NOT EXISTS prev_entry_hash BYTEA;
ALTER TABLE transparency_log_entries ADD COLUMN IF NOT EXISTS payload      JSONB;
ALTER TABLE transparency_log_entries ADD COLUMN IF NOT EXISTS signature    BYTEA;
ALTER TABLE transparency_log_entries ADD COLUMN IF NOT EXISTS kid          TEXT;
ALTER TABLE transparency_log_entries ADD COLUMN IF NOT EXISTS co_signature BYTEA;
ALTER TABLE transparency_log_entries ADD COLUMN IF NOT EXISTS co_kid       TEXT;
ALTER TABLE transparency_log_entries ADD COLUMN IF NOT EXISTS co_signed_at TIMESTAMPTZ;
ALTER TABLE transparency_log_entries ADD COLUMN IF NOT EXISTS co_signed_by TEXT;
ALTER TABLE transparency_log_entries ADD COLUMN IF NOT EXISTS is_locked    BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE transparency_log_entries ADD COLUMN IF NOT EXISTS logged_at    TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE transparency_log_entries ADD COLUMN IF NOT EXISTS created_at   TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_tlog_tenant
    ON transparency_log_entries(tenant_id, logged_at DESC);
CREATE INDEX IF NOT EXISTS idx_tlog_case
    ON transparency_log_entries(case_id, logged_at DESC);
CREATE INDEX IF NOT EXISTS idx_tlog_acr
    ON transparency_log_entries(acr_id);

ALTER TABLE transparency_log_entries ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY tlog_tenant_isolation
        ON transparency_log_entries
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
EXCEPTION WHEN duplicate_object THEN NULL; END; $$;


-- =============================================================================
-- BLOCK B: Domain 4 — Canonical Logistics Truth (tables missing from baseline)
-- =============================================================================

-- ── B1: stops — individual route waypoints for multi-leg shipments ────────────
CREATE TABLE IF NOT EXISTS stops (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    shipment_id     UUID REFERENCES shipments(id),
    leg_id          UUID REFERENCES shipment_legs(id),
    stop_sequence   INTEGER NOT NULL DEFAULT 1,
    facility_id     UUID REFERENCES facilities(id),
    location_name   TEXT,
    location_code   TEXT,
    country_code    TEXT,
    scheduled_arrival   TIMESTAMPTZ,
    actual_arrival      TIMESTAMPTZ,
    scheduled_departure TIMESTAMPTZ,
    actual_departure    TIMESTAMPTZ,
    stop_type       TEXT NOT NULL DEFAULT 'WAYPOINT'
                    CHECK (stop_type IN ('ORIGIN','WAYPOINT','TRANSSHIPMENT','DESTINATION')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_stops_shipment ON stops(tenant_id, shipment_id);
ALTER TABLE stops ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY stops_tenant_isolation ON stops
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
EXCEPTION WHEN duplicate_object THEN NULL; END; $$;


-- ── B2: suppliers — vendor/manufacturer master ────────────────────────────────
CREATE TABLE IF NOT EXISTS suppliers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    supplier_code   TEXT NOT NULL,
    name            TEXT NOT NULL,
    country_code    TEXT,
    city            TEXT,
    contact_email   TEXT,
    contact_phone   TEXT,
    payment_terms   TEXT,
    currency        TEXT NOT NULL DEFAULT 'INR',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, supplier_code)
);
CREATE INDEX IF NOT EXISTS idx_suppliers_tenant ON suppliers(tenant_id, is_active);
ALTER TABLE suppliers ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY suppliers_tenant_isolation ON suppliers
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
EXCEPTION WHEN duplicate_object THEN NULL; END; $$;


-- ── B3: warehouses — physical storage locations ────────────────────────────────
CREATE TABLE IF NOT EXISTS warehouses (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    warehouse_code  TEXT NOT NULL,
    name            TEXT NOT NULL,
    facility_id     UUID REFERENCES facilities(id),
    country_code    TEXT,
    city            TEXT,
    capacity_sqm    NUMERIC(12,2),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, warehouse_code)
);
CREATE INDEX IF NOT EXISTS idx_warehouses_tenant ON warehouses(tenant_id, is_active);
ALTER TABLE warehouses ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY warehouses_tenant_isolation ON warehouses
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
EXCEPTION WHEN duplicate_object THEN NULL; END; $$;


-- ── B4: equipment_types — truck/container/pallet types ────────────────────────
CREATE TABLE IF NOT EXISTS equipment_types (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    code            TEXT NOT NULL,
    name            TEXT NOT NULL,
    category        TEXT NOT NULL DEFAULT 'VEHICLE'
                    CHECK (category IN ('VEHICLE','CONTAINER','PALLET','BOX','BULK')),
    max_weight_kg   NUMERIC(10,2),
    max_volume_cbm  NUMERIC(10,2),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, code)
);
CREATE INDEX IF NOT EXISTS idx_equipment_types_tenant ON equipment_types(tenant_id);
ALTER TABLE equipment_types ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY equipment_types_tenant_isolation ON equipment_types
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
EXCEPTION WHEN duplicate_object THEN NULL; END; $$;


-- ── B5: service_levels — SLA tiers (EXPRESS, STANDARD, ECONOMY, etc.) ─────────
CREATE TABLE IF NOT EXISTS service_levels (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    carrier_id      TEXT,
    code            TEXT NOT NULL,
    name            TEXT NOT NULL,
    transit_days_min INTEGER,
    transit_days_max INTEGER,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, carrier_id, code)
);
CREATE INDEX IF NOT EXISTS idx_service_levels_carrier ON service_levels(tenant_id, carrier_id);
ALTER TABLE service_levels ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY service_levels_tenant_isolation ON service_levels
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
EXCEPTION WHEN duplicate_object THEN NULL; END; $$;


-- ── B6: purchase_orders — procurement PO header ────────────────────────────────
CREATE TABLE IF NOT EXISTS purchase_orders (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    po_number       TEXT NOT NULL,
    supplier_id     UUID REFERENCES suppliers(id),
    status          TEXT NOT NULL DEFAULT 'DRAFT'
                    CHECK (status IN ('DRAFT','CONFIRMED','SHIPPED','RECEIVED','CANCELLED','CLOSED')),
    total_amount    NUMERIC(18,4),
    currency        TEXT NOT NULL DEFAULT 'INR',
    ordered_at      TIMESTAMPTZ,
    expected_delivery DATE,
    actual_delivery   DATE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, po_number)
);
CREATE INDEX IF NOT EXISTS idx_purchase_orders_tenant ON purchase_orders(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_purchase_orders_supplier ON purchase_orders(tenant_id, supplier_id);
ALTER TABLE purchase_orders ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY purchase_orders_tenant_isolation ON purchase_orders
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
EXCEPTION WHEN duplicate_object THEN NULL; END; $$;


-- ── B7: accessorials — surcharge line items on shipments ──────────────────────
CREATE TABLE IF NOT EXISTS accessorials (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    shipment_id     UUID REFERENCES shipments(id),
    invoice_id      UUID REFERENCES canonical_invoices(id),
    charge_code     TEXT NOT NULL,
    description     TEXT,
    amount          NUMERIC(18,4) NOT NULL,
    currency        TEXT NOT NULL DEFAULT 'INR',
    status          TEXT NOT NULL DEFAULT 'BILLED'
                    CHECK (status IN ('BILLED','DISPUTED','APPROVED','WAIVED','CREDITED')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_accessorials_shipment ON accessorials(tenant_id, shipment_id);
CREATE INDEX IF NOT EXISTS idx_accessorials_invoice  ON accessorials(tenant_id, invoice_id);
ALTER TABLE accessorials ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY accessorials_tenant_isolation ON accessorials
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
EXCEPTION WHEN duplicate_object THEN NULL; END; $$;


-- ── B8: disputes — formal dispute records linking to cases ────────────────────
CREATE TABLE IF NOT EXISTS disputes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    case_id         UUID REFERENCES cases(id),
    invoice_id      UUID REFERENCES canonical_invoices(id),
    carrier_id      TEXT,
    dispute_type    TEXT NOT NULL DEFAULT 'RATE_MISMATCH'
                    CHECK (dispute_type IN ('RATE_MISMATCH','ACCESSORIAL','DUPLICATE',
                                            'CLAIM_DENIAL','SLA_BREACH','OTHER')),
    disputed_amount NUMERIC(18,4),
    currency        TEXT NOT NULL DEFAULT 'INR',
    status          TEXT NOT NULL DEFAULT 'OPEN'
                    CHECK (status IN ('OPEN','IN_PROGRESS','RESOLVED','WITHDRAWN','ESCALATED')),
    resolution      TEXT,
    resolved_amount NUMERIC(18,4),
    opened_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_disputes_case    ON disputes(tenant_id, case_id);
CREATE INDEX IF NOT EXISTS idx_disputes_invoice ON disputes(tenant_id, invoice_id);
CREATE INDEX IF NOT EXISTS idx_disputes_status  ON disputes(tenant_id, status);
ALTER TABLE disputes ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY disputes_tenant_isolation ON disputes
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
EXCEPTION WHEN duplicate_object THEN NULL; END; $$;


-- ── B9: inventory_movements — warehouse stock in/out events ──────────────────
CREATE TABLE IF NOT EXISTS inventory_movements (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    warehouse_id    UUID REFERENCES warehouses(id),
    shipment_id     UUID REFERENCES shipments(id),
    po_id           UUID REFERENCES purchase_orders(id),
    sku_code        TEXT NOT NULL,
    movement_type   TEXT NOT NULL DEFAULT 'INBOUND'
                    CHECK (movement_type IN ('INBOUND','OUTBOUND','TRANSFER','ADJUSTMENT')),
    quantity        NUMERIC(12,2) NOT NULL,
    unit_cost       NUMERIC(12,4),
    currency        TEXT NOT NULL DEFAULT 'INR',
    reference_doc   TEXT,
    moved_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_inv_movements_warehouse ON inventory_movements(tenant_id, warehouse_id, moved_at DESC);
CREATE INDEX IF NOT EXISTS idx_inv_movements_sku       ON inventory_movements(tenant_id, sku_code, moved_at DESC);
ALTER TABLE inventory_movements ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY inventory_movements_tenant_isolation ON inventory_movements
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
EXCEPTION WHEN duplicate_object THEN NULL; END; $$;


-- =============================================================================
-- BLOCK C: Domain 5 — Commercial Reference Data (missing from baseline)
-- =============================================================================

-- ── C1: master_service_agreements — top-level carrier MSA ─────────────────────
CREATE TABLE IF NOT EXISTS master_service_agreements (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    carrier_id      TEXT NOT NULL,
    msa_reference   TEXT NOT NULL,
    title           TEXT,
    effective_from  DATE NOT NULL,
    effective_to    DATE,
    status          TEXT NOT NULL DEFAULT 'ACTIVE'
                    CHECK (status IN ('DRAFT','ACTIVE','EXPIRED','TERMINATED')),
    signed_at       DATE,
    signed_by       TEXT,
    document_url    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, msa_reference)
);
CREATE INDEX IF NOT EXISTS idx_msa_tenant_carrier ON master_service_agreements(tenant_id, carrier_id, status);
ALTER TABLE master_service_agreements ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY msa_tenant_isolation ON master_service_agreements
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
EXCEPTION WHEN duplicate_object THEN NULL; END; $$;


-- ── C2: carrier_agreements — per-lane/service agreement under an MSA ──────────
CREATE TABLE IF NOT EXISTS carrier_agreements (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    msa_id          UUID REFERENCES master_service_agreements(id),
    carrier_id      TEXT NOT NULL,
    agreement_code  TEXT NOT NULL,
    service_level   TEXT,
    effective_from  DATE NOT NULL,
    effective_to    DATE,
    status          TEXT NOT NULL DEFAULT 'ACTIVE'
                    CHECK (status IN ('ACTIVE','EXPIRED','SUPERSEDED','TERMINATED')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, agreement_code)
);
CREATE INDEX IF NOT EXISTS idx_carrier_agreements_tenant  ON carrier_agreements(tenant_id, carrier_id, status);
CREATE INDEX IF NOT EXISTS idx_carrier_agreements_msa     ON carrier_agreements(msa_id);
ALTER TABLE carrier_agreements ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY carrier_agreements_tenant_isolation ON carrier_agreements
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
EXCEPTION WHEN duplicate_object THEN NULL; END; $$;


-- ── C3: lanes — origin-destination pairs ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS lanes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    lane_code       TEXT NOT NULL,
    origin_city     TEXT,
    origin_country  TEXT,
    destination_city TEXT,
    destination_country TEXT,
    distance_km     NUMERIC(10,2),
    transit_days    INTEGER,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, lane_code)
);
CREATE INDEX IF NOT EXISTS idx_lanes_tenant ON lanes(tenant_id, is_active);
ALTER TABLE lanes ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY lanes_tenant_isolation ON lanes
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
EXCEPTION WHEN duplicate_object THEN NULL; END; $$;


-- ── C4: lane_bundles — named groupings of lanes (e.g. "Mumbai Metro") ─────────
CREATE TABLE IF NOT EXISTS lane_bundles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    bundle_code     TEXT NOT NULL,
    name            TEXT NOT NULL,
    carrier_id      TEXT,
    agreement_id    UUID REFERENCES carrier_agreements(id),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, bundle_code)
);
CREATE TABLE IF NOT EXISTS lane_bundle_members (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bundle_id       UUID NOT NULL REFERENCES lane_bundles(id),
    lane_id         UUID NOT NULL REFERENCES lanes(id),
    UNIQUE (bundle_id, lane_id)
);
CREATE INDEX IF NOT EXISTS idx_lane_bundles_tenant ON lane_bundles(tenant_id, carrier_id);
ALTER TABLE lane_bundles ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY lane_bundles_tenant_isolation ON lane_bundles
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
EXCEPTION WHEN duplicate_object THEN NULL; END; $$;


-- ── C5: rate_schedules — versioned rate tariff header ─────────────────────────
CREATE TABLE IF NOT EXISTS rate_schedules (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    schedule_code   TEXT NOT NULL,
    carrier_id      TEXT NOT NULL,
    agreement_id    UUID REFERENCES carrier_agreements(id),
    currency        TEXT NOT NULL DEFAULT 'INR',
    effective_from  DATE NOT NULL,
    effective_to    DATE,
    status          TEXT NOT NULL DEFAULT 'ACTIVE'
                    CHECK (status IN ('DRAFT','ACTIVE','EXPIRED','SUPERSEDED')),
    approved_by     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, schedule_code, effective_from)
);
CREATE INDEX IF NOT EXISTS idx_rate_schedules_carrier ON rate_schedules(tenant_id, carrier_id, status);
ALTER TABLE rate_schedules ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY rate_schedules_tenant_isolation ON rate_schedules
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
EXCEPTION WHEN duplicate_object THEN NULL; END; $$;


-- ── C6: charge_components — line items within a rate schedule ─────────────────
CREATE TABLE IF NOT EXISTS charge_components (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    schedule_id     UUID NOT NULL REFERENCES rate_schedules(id),
    lane_id         UUID REFERENCES lanes(id),
    charge_code     TEXT NOT NULL,
    charge_type     TEXT NOT NULL DEFAULT 'BASE'
                    CHECK (charge_type IN ('BASE','FUEL','ACCESSORIAL','HANDLING','INSURANCE','OTHER')),
    basis           TEXT NOT NULL DEFAULT 'PER_SHIPMENT'
                    CHECK (basis IN ('PER_SHIPMENT','PER_KG','PER_KM','PER_UNIT','FLAT','PERCENTAGE')),
    rate_value      NUMERIC(18,6) NOT NULL,
    min_charge      NUMERIC(18,4),
    max_charge      NUMERIC(18,4),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_charge_components_schedule ON charge_components(tenant_id, schedule_id);
ALTER TABLE charge_components ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY charge_components_tenant_isolation ON charge_components
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
EXCEPTION WHEN duplicate_object THEN NULL; END; $$;


-- ── C7: charge_tiers — volume/weight-based break points ──────────────────────
CREATE TABLE IF NOT EXISTS charge_tiers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    component_id    UUID NOT NULL REFERENCES charge_components(id),
    tier_from       NUMERIC(12,2) NOT NULL,
    tier_to         NUMERIC(12,2),
    rate_value      NUMERIC(18,6) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_charge_tiers_component ON charge_tiers(component_id);
ALTER TABLE charge_tiers ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY charge_tiers_tenant_isolation ON charge_tiers
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
EXCEPTION WHEN duplicate_object THEN NULL; END; $$;


-- ── C8: contract_rate_versions — versioning/supersession for contract_rates ───
-- contract_rates already exists; this table tracks its version history.
CREATE TABLE IF NOT EXISTS contract_rate_versions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    rate_id         UUID NOT NULL REFERENCES contract_rates(id),
    version_number  INTEGER NOT NULL DEFAULT 1,
    change_reason   TEXT,
    changed_by      TEXT,
    snapshot        JSONB NOT NULL,         -- full row snapshot at version point
    superseded_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, rate_id, version_number)
);
CREATE INDEX IF NOT EXISTS idx_contract_rate_versions_rate ON contract_rate_versions(rate_id, version_number DESC);
ALTER TABLE contract_rate_versions ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY contract_rate_versions_tenant_isolation ON contract_rate_versions
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
EXCEPTION WHEN duplicate_object THEN NULL; END; $$;


-- ── C9: accessorial_tariffs — carrier-published accessorial charge schedules ──
CREATE TABLE IF NOT EXISTS accessorial_tariffs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    carrier_id      TEXT NOT NULL,
    charge_code     TEXT NOT NULL,
    description     TEXT,
    rate_value      NUMERIC(18,6) NOT NULL,
    currency        TEXT NOT NULL DEFAULT 'INR',
    basis           TEXT NOT NULL DEFAULT 'FLAT'
                    CHECK (basis IN ('FLAT','PER_KG','PER_UNIT','PERCENTAGE')),
    effective_from  DATE NOT NULL,
    effective_to    DATE,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, carrier_id, charge_code, effective_from)
);
CREATE INDEX IF NOT EXISTS idx_accessorial_tariffs_carrier ON accessorial_tariffs(tenant_id, carrier_id, is_active);
ALTER TABLE accessorial_tariffs ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY accessorial_tariffs_tenant_isolation ON accessorial_tariffs
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
EXCEPTION WHEN duplicate_object THEN NULL; END; $$;


-- ── C10: spot_quotes — one-off carrier price quotes outside contract rates ─────
CREATE TABLE IF NOT EXISTS spot_quotes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    quote_reference TEXT NOT NULL,
    carrier_id      TEXT NOT NULL,
    lane_id         UUID REFERENCES lanes(id),
    quoted_amount   NUMERIC(18,4) NOT NULL,
    currency        TEXT NOT NULL DEFAULT 'INR',
    valid_until     DATE,
    status          TEXT NOT NULL DEFAULT 'OPEN'
                    CHECK (status IN ('OPEN','ACCEPTED','EXPIRED','DECLINED')),
    shipment_id     UUID REFERENCES shipments(id),
    quoted_by       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, quote_reference)
);
CREATE INDEX IF NOT EXISTS idx_spot_quotes_carrier ON spot_quotes(tenant_id, carrier_id, status);
ALTER TABLE spot_quotes ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY spot_quotes_tenant_isolation ON spot_quotes
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
EXCEPTION WHEN duplicate_object THEN NULL; END; $$;
