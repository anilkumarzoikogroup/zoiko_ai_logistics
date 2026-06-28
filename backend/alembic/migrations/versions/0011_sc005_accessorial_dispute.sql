-- SC-005 Accessorial Charge Dispute — schema additions
-- Adds accessorial_charges and accessorial_tariff_caps tables
-- Also extends cases.case_type_check to include ACCESSORIAL_DISPUTE

-- accessorial_tariff_caps: contracted cap per carrier + charge_type
CREATE TABLE IF NOT EXISTS accessorial_tariff_caps (
    id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      UUID         NOT NULL,
    carrier_id     VARCHAR(100) NOT NULL,
    charge_type    VARCHAR(50)  NOT NULL,
    cap_amount     NUMERIC(15,2) NOT NULL,
    tariff_id      VARCHAR(100),
    tariff_version VARCHAR(50),
    currency       VARCHAR(3)   NOT NULL DEFAULT 'INR',
    effective_from TIMESTAMPTZ,
    effective_to   TIMESTAMPTZ,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_accessorial_cap UNIQUE (tenant_id, carrier_id, charge_type)
);

-- accessorial_charges: individual charge lines per case/invoice
CREATE TABLE IF NOT EXISTS accessorial_charges (
    id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      UUID         NOT NULL,
    case_id        UUID         REFERENCES cases(id) ON DELETE CASCADE,
    invoice_id     UUID,
    charge_type    VARCHAR(50)  NOT NULL,
    billed_amount  NUMERIC(15,2) NOT NULL,
    contracted_cap NUMERIC(15,2) NOT NULL,
    tariff_id      VARCHAR(100),
    tariff_version VARCHAR(50),
    dispute_amount NUMERIC(15,2) GENERATED ALWAYS AS (GREATEST(0.00, billed_amount - contracted_cap)) STORED,
    currency       VARCHAR(3)   NOT NULL DEFAULT 'INR',
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Enable RLS
ALTER TABLE accessorial_tariff_caps ENABLE ROW LEVEL SECURITY;
ALTER TABLE accessorial_charges     ENABLE ROW LEVEL SECURITY;

-- Extend cases case_type_check to include ACCESSORIAL_DISPUTE (drop + recreate)
DO $$ BEGIN
    ALTER TABLE cases DROP CONSTRAINT IF EXISTS cases_case_type_check;
    ALTER TABLE cases DROP CONSTRAINT IF EXISTS chk_cases_case_type;
    ALTER TABLE cases DROP CONSTRAINT IF EXISTS case_type_check;
    ALTER TABLE cases ADD CONSTRAINT cases_case_type_check
        CHECK (case_type = ANY (ARRAY[
            'INVOICE_OVERCHARGE',
            'CARRIER_CLAIM',
            'SHIPMENT_EXCEPTION',
            'SCORECARD_BREACH',
            'ACCESSORIAL_DISPUTE'
        ]));
EXCEPTION WHEN others THEN NULL;
END $$;

-- Extend chk_cases_subject to allow ACCESSORIAL_DISPUTE
DO $$ BEGIN
    ALTER TABLE cases DROP CONSTRAINT IF EXISTS chk_cases_subject;
    ALTER TABLE cases ADD CONSTRAINT chk_cases_subject CHECK (
        (case_type = 'INVOICE_OVERCHARGE'   AND invoice_id IS NOT NULL AND claim_id IS NULL)
        OR (case_type = 'CARRIER_CLAIM'     AND claim_id IS NOT NULL   AND invoice_id IS NULL)
        OR (case_type = 'SHIPMENT_EXCEPTION' AND invoice_id IS NULL    AND claim_id IS NULL)
        OR (case_type = 'SCORECARD_BREACH'  AND invoice_id IS NULL     AND claim_id IS NULL)
        OR (case_type = 'ACCESSORIAL_DISPUTE' AND claim_id IS NULL)
    );
EXCEPTION WHEN others THEN NULL;
END $$;
