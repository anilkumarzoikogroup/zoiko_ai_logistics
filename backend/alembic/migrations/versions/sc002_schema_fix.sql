-- ===== SC-002 schema catch-up fix =====
-- Safe to run on any existing DB — fully idempotent.
-- Ensures cases.claim_id, cases.case_type, and all SC-002 indexes exist
-- regardless of whether migration 0002 ran successfully.

-- 1. Add columns to cases if missing
ALTER TABLE cases ADD COLUMN IF NOT EXISTS claim_id  UUID;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS case_type TEXT NOT NULL DEFAULT 'INVOICE_OVERCHARGE'::text;

-- 2. Ensure claims and claim_lines tables exist
CREATE TABLE IF NOT EXISTS claims (
    id              UUID         NOT NULL DEFAULT gen_random_uuid(),
    tenant_id       UUID         NOT NULL,
    case_id         UUID,
    shipment_id     UUID,
    claim_type      TEXT         NOT NULL DEFAULT 'OVERCHARGE'::text,
    claimed_amount  NUMERIC(18,4) NOT NULL DEFAULT 0,
    approved_amount NUMERIC(18,4),
    currency        TEXT         NOT NULL DEFAULT 'USD'::text,
    status          TEXT         NOT NULL DEFAULT 'OPEN'::text,
    filed_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    resolved_at     TIMESTAMP WITH TIME ZONE,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    source_record_id UUID,
    carrier_id      TEXT         NOT NULL DEFAULT ''::text,
    claim_hash      BYTEA,
    claim_reference TEXT         NOT NULL DEFAULT ''::text
);

CREATE TABLE IF NOT EXISTS claim_lines (
    id              UUID         NOT NULL,
    tenant_id       UUID         NOT NULL,
    claim_id        UUID         NOT NULL,
    line_number     INTEGER      NOT NULL,
    description     TEXT         NOT NULL DEFAULT ''::text,
    claimed_amount  NUMERIC      NOT NULL,
    currency        TEXT         NOT NULL,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- 3. Primary keys (idempotent via DO block)
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='claims_pkey' AND conrelid='claims'::regclass) THEN
        ALTER TABLE claims ADD CONSTRAINT claims_pkey PRIMARY KEY (id);
    END IF;
END; $$;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='claim_lines_pkey' AND conrelid='claim_lines'::regclass) THEN
        ALTER TABLE claim_lines ADD CONSTRAINT claim_lines_pkey PRIMARY KEY (id);
    END IF;
END; $$;

-- 4. Check constraints
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='cases_case_type_check' AND conrelid='cases'::regclass) THEN
        ALTER TABLE cases ADD CONSTRAINT cases_case_type_check
            CHECK (case_type = ANY (ARRAY['INVOICE_OVERCHARGE','CARRIER_CLAIM']));
    END IF;
END; $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='chk_cases_subject' AND conrelid='cases'::regclass) THEN
        ALTER TABLE cases ADD CONSTRAINT chk_cases_subject CHECK (
            ((case_type = 'INVOICE_OVERCHARGE') AND (invoice_id IS NOT NULL) AND (claim_id IS NULL))
            OR
            ((case_type = 'CARRIER_CLAIM')      AND (claim_id IS NOT NULL)  AND (invoice_id IS NULL))
        );
    END IF;
END; $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='chk_claims_status' AND conrelid='claims'::regclass) THEN
        ALTER TABLE claims ADD CONSTRAINT chk_claims_status
            CHECK (status = ANY (ARRAY['OPEN','SUBMITTED','UNDER_CARRIER_REVIEW','COUNTERED',
                                       'PARTIALLY_ACCEPTED','ACCEPTED','REJECTED','WITHDRAWN','CLOSED']));
    END IF;
END; $$;

-- 5. Foreign keys
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='cases_claim_id_fkey' AND conrelid='cases'::regclass) THEN
        ALTER TABLE cases ADD CONSTRAINT cases_claim_id_fkey FOREIGN KEY (claim_id) REFERENCES claims(id);
    END IF;
END; $$;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='claims_case_id_fkey' AND conrelid='claims'::regclass) THEN
        ALTER TABLE claims ADD CONSTRAINT claims_case_id_fkey FOREIGN KEY (case_id) REFERENCES cases(id);
    END IF;
END; $$;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='claims_tenant_id_fkey' AND conrelid='claims'::regclass) THEN
        ALTER TABLE claims ADD CONSTRAINT claims_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
    END IF;
END; $$;

-- 6. Critical indexes required by ON CONFLICT in application code
CREATE UNIQUE INDEX IF NOT EXISTS uq_cases_tenant_claim
    ON cases (tenant_id, claim_id)
    WHERE claim_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_claims_tenant_reference
    ON claims (tenant_id, claim_reference)
    WHERE claim_reference <> '';

CREATE UNIQUE INDEX IF NOT EXISTS uq_claim_lines_claim_line
    ON claim_lines (claim_id, line_number);

CREATE INDEX IF NOT EXISTS ix_claim_lines_tenant
    ON claim_lines (tenant_id);
