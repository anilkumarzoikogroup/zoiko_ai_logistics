-- =============================================================================
-- Migration 0006 — Supplementary Tracking Tables
-- =============================================================================
-- Adds tables required by Build Map domains 8–12 that were not covered in
-- migrations 0001–0005. Safe to run on any existing DB — all statements are
-- idempotent (CREATE TABLE IF NOT EXISTS, ADD COLUMN IF NOT EXISTS).
-- =============================================================================


-- -----------------------------------------------------------------------------
-- DOMAIN 8 — Reasoning: agent_invocations
-- Tracks every AI agent call per case for audit, replay, and cost analysis.
-- Append-only: never UPDATE or DELETE.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_invocations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    case_id         UUID REFERENCES cases(id),
    agent_name      TEXT NOT NULL,
    agent_version   TEXT NOT NULL DEFAULT 'v1',
    input_hash      BYTEA,          -- SHA-256 of canonicalized input payload
    output_hash     BYTEA,          -- SHA-256 of canonicalized output payload
    confidence      NUMERIC(6,4),
    latency_ms      INTEGER,
    model_id        TEXT,           -- e.g. "groq/mixtral-8x7b-32768"
    status          TEXT NOT NULL DEFAULT 'COMPLETED'
                    CHECK (status IN ('STARTED','COMPLETED','FAILED','TIMED_OUT')),
    error_message   TEXT,
    invoked_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_invocations_case
    ON agent_invocations(tenant_id, case_id);
CREATE INDEX IF NOT EXISTS idx_agent_invocations_agent
    ON agent_invocations(tenant_id, agent_name, invoked_at DESC);

-- RLS: tenants only see their own invocations
ALTER TABLE agent_invocations ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY agent_invocations_tenant_isolation
        ON agent_invocations
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
EXCEPTION WHEN duplicate_object THEN NULL; END; $$;


-- -----------------------------------------------------------------------------
-- DOMAIN 9 — Governance: token_revocations
-- Explicit revocations of governance tokens before their natural expiry.
-- Append-only: a token that has been revoked cannot be un-revoked.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS token_revocations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    token_id        UUID NOT NULL REFERENCES governance_tokens(id),
    revoked_by_sub  TEXT NOT NULL,
    reason          TEXT NOT NULL,
    revocation_hash BYTEA,          -- SHA-256("zoiko.token.revocation.v1:" + jcs_payload)
    signature       BYTEA,
    kid             TEXT,
    revoked_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (token_id)               -- one revocation record per token (idempotent)
);

CREATE INDEX IF NOT EXISTS idx_token_revocations_token
    ON token_revocations(token_id);
CREATE INDEX IF NOT EXISTS idx_token_revocations_tenant
    ON token_revocations(tenant_id, revoked_at DESC);

ALTER TABLE token_revocations ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY token_revocations_tenant_isolation
        ON token_revocations
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
EXCEPTION WHEN duplicate_object THEN NULL; END; $$;


-- -----------------------------------------------------------------------------
-- DOMAIN 10 — Execution: connector_registrations
-- Registry of certified carrier API connectors. Gate 8 of the execution
-- gateway checks here when CONNECTOR_REGISTRY_URL is not configured.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS connector_registrations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    connector_code  TEXT NOT NULL,  -- e.g. "BLUEDART_IN", "FEDEX_US"
    carrier_id      TEXT NOT NULL,
    endpoint_url    TEXT,
    auth_scheme     TEXT NOT NULL DEFAULT 'API_KEY'
                    CHECK (auth_scheme IN ('API_KEY','OAUTH2','MTLS','HMAC')),
    status          TEXT NOT NULL DEFAULT 'ACTIVE'
                    CHECK (status IN ('ACTIVE','INACTIVE','SUSPENDED','DEPRECATED')),
    certified_by    TEXT,           -- sub of the admin who certified
    certified_at    TIMESTAMPTZ,
    expires_at      TIMESTAMPTZ,
    capabilities    JSONB,          -- ["CREDIT_MEMO","DEBIT_NOTE","CLAIM_SETTLEMENT"]
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, connector_code)
);

CREATE INDEX IF NOT EXISTS idx_connector_registrations_tenant
    ON connector_registrations(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_connector_registrations_carrier
    ON connector_registrations(tenant_id, carrier_id);

ALTER TABLE connector_registrations ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY connector_registrations_tenant_isolation
        ON connector_registrations
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
EXCEPTION WHEN duplicate_object THEN NULL; END; $$;


-- -----------------------------------------------------------------------------
-- DOMAIN 10 — Execution: connector_dispatches
-- Per-envelope log of calls made to the carrier connector during execution.
-- Append-only: never UPDATE or DELETE.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS connector_dispatches (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    envelope_id     UUID REFERENCES execution_envelopes(id),
    registration_id UUID REFERENCES connector_registrations(id),
    connector_code  TEXT NOT NULL,
    carrier_id      TEXT,
    action          TEXT NOT NULL,  -- "CREDIT_MEMO", "DEBIT_NOTE", "SETTLE_CLAIM", "ISSUE_SLA_CREDIT"
    amount          NUMERIC(18,4),
    currency        TEXT,
    request_hash    BYTEA,          -- SHA-256 of request payload
    response_code   INTEGER,
    response_body   JSONB,
    latency_ms      INTEGER,
    status          TEXT NOT NULL DEFAULT 'SENT'
                    CHECK (status IN ('SENT','DELIVERED','FAILED','REJECTED','TIMED_OUT')),
    dispatched_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    acknowledged_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_connector_dispatches_envelope
    ON connector_dispatches(envelope_id);
CREATE INDEX IF NOT EXISTS idx_connector_dispatches_tenant
    ON connector_dispatches(tenant_id, dispatched_at DESC);

ALTER TABLE connector_dispatches ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY connector_dispatches_tenant_isolation
        ON connector_dispatches
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
EXCEPTION WHEN duplicate_object THEN NULL; END; $$;


-- -----------------------------------------------------------------------------
-- DOMAIN 11 — Reconciliation: aging_buckets
-- Snapshot table tracking how long expected_recoveries have been outstanding.
-- Written by the nightly aging job; used by the reconciliation dashboard.
-- Not append-only: rows are upserted daily (ON CONFLICT DO UPDATE).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS aging_buckets (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    expected_id     UUID NOT NULL REFERENCES expected_recoveries(id),
    case_id         UUID REFERENCES cases(id),
    carrier_id      TEXT,
    expected_amount NUMERIC(18,4) NOT NULL,
    currency        TEXT NOT NULL DEFAULT 'INR',
    age_days        INTEGER NOT NULL,
    bucket          TEXT NOT NULL   -- "0-30","31-60","61-90","91-180","180+"
                    CHECK (bucket IN ('0-30','31-60','61-90','91-180','180+')),
    recovery_status TEXT,           -- mirrors expected_recoveries.status
    snapshot_date   DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, expected_id, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_aging_buckets_tenant_date
    ON aging_buckets(tenant_id, snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_aging_buckets_bucket
    ON aging_buckets(tenant_id, bucket, snapshot_date DESC);

ALTER TABLE aging_buckets ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY aging_buckets_tenant_isolation
        ON aging_buckets
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
EXCEPTION WHEN duplicate_object THEN NULL; END; $$;


-- -----------------------------------------------------------------------------
-- DOMAIN 12 — ACR/Audit: transparency_log_entries
-- Co-signed append-only transparency log for ACR issuance and key events.
-- Each row is independently verifiable (hash chain from prev_entry_hash).
-- Append-only: never UPDATE or DELETE.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS transparency_log_entries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    case_id         UUID REFERENCES cases(id),
    acr_id          UUID REFERENCES action_certification_records(id),
    entry_type      TEXT NOT NULL
                    CHECK (entry_type IN (
                        'ACR_ISSUED','TOKEN_ISSUED','TOKEN_CONSUMED',
                        'EXECUTION_DISPATCHED','RECOVERY_CLOSED',
                        'KEY_ROTATION','AUDIT_CHECKPOINT'
                    )),
    entry_hash      BYTEA NOT NULL,
    prev_entry_hash BYTEA,
    payload         JSONB NOT NULL,
    signature       BYTEA NOT NULL,
    kid             TEXT NOT NULL,
    co_signature    BYTEA,
    co_kid          TEXT,
    co_signed_at    TIMESTAMPTZ,
    co_signed_by    TEXT,
    is_locked       BOOLEAN NOT NULL DEFAULT FALSE,
    logged_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Schema drift guards for pre-existing transparency_log_entries table
ALTER TABLE transparency_log_entries ADD COLUMN IF NOT EXISTS case_id UUID REFERENCES cases(id);
ALTER TABLE transparency_log_entries ADD COLUMN IF NOT EXISTS logged_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_transparency_log_tenant
    ON transparency_log_entries(tenant_id, logged_at DESC);
CREATE INDEX IF NOT EXISTS idx_transparency_log_case
    ON transparency_log_entries(case_id, logged_at DESC);
CREATE INDEX IF NOT EXISTS idx_transparency_log_acr
    ON transparency_log_entries(acr_id);

ALTER TABLE transparency_log_entries ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY transparency_log_tenant_isolation
        ON transparency_log_entries
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
EXCEPTION WHEN duplicate_object THEN NULL; END; $$;


-- -----------------------------------------------------------------------------
-- DOMAIN 5 — Commercial Reference: claim_policy_caps
-- Per-tenant claim amount caps used by SC-002 validation to flag oversized
-- claims before they advance to canonical truth.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS claim_policy_caps (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    carrier_id      TEXT,           -- NULL = applies to all carriers for this tenant
    claim_type      TEXT,           -- NULL = applies to all claim types
    max_claim_amount NUMERIC(18,4) NOT NULL,
    currency        TEXT NOT NULL DEFAULT 'INR',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    effective_from  DATE NOT NULL DEFAULT CURRENT_DATE,
    effective_to    DATE,
    created_by      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, carrier_id, claim_type, effective_from)
);

CREATE INDEX IF NOT EXISTS idx_claim_policy_caps_tenant
    ON claim_policy_caps(tenant_id, is_active, effective_from DESC);

ALTER TABLE claim_policy_caps ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    CREATE POLICY claim_policy_caps_tenant_isolation
        ON claim_policy_caps
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
EXCEPTION WHEN duplicate_object THEN NULL; END; $$;


-- -----------------------------------------------------------------------------
-- Seed: default claim policy caps for the demo tenant
-- Max claim = 1,000,000 INR — well above the SC-002 demo amount of ₹8,000.
-- -----------------------------------------------------------------------------
INSERT INTO claim_policy_caps (id, tenant_id, max_claim_amount, currency, is_active)
SELECT
    gen_random_uuid(),
    t.id,
    1000000.00,
    'INR',
    TRUE
FROM tenants t
WHERE NOT EXISTS (
    SELECT 1 FROM claim_policy_caps c WHERE c.tenant_id = t.id
)
LIMIT 5;
