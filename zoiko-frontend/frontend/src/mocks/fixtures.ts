import type {
  Case, CanonicalInvoice, ValidationResult, EvidenceBundle,
  Finding, DecisionProposal, GovernanceToken, GovernanceDecision, CaseEvent,
  KafkaEvent, DashboardStats, SourceRecord
} from "@/types";

const NOW = new Date();
const T = (mins: number) => new Date(NOW.getTime() - mins * 60_000).toISOString();

export const mockStats: DashboardStats = {
  total_cases: 47,
  pending_approval: 12,
  approved: 28,
  total_recovered: 1247500,
  avg_confidence: 0.91,
};

const carriers = ["BlueDart", "Delhivery", "FedEx", "DTDC", "Gati"];

function rndHash(len = 64): string {
  const chars = "0123456789abcdef";
  let s = "0x";
  for (let i = 0; i < len; i++) s += chars[Math.floor(Math.random() * 16)];
  return s;
}

// Deterministic states so every reload gives a consistent queue spread
const FIXED_STATES: Case["state"][] = [
  "APPROVAL_PENDING",   // 0 — SC-001 (overridden below)
  "FINDING_GENERATED",       // 1 — analyst queue
  "NEW",             // 2 — analyst queue
  "EVIDENCE_PENDING", // 3 — analyst queue
  "APPROVAL_PENDING",   // 4 — manager queue
  "EXECUTION_READY",           // 5
  "DISPATCHED",           // 6
  "OUTCOME_RECORDED",         // 7
  "CLOSED",             // 8
  "NEW",             // 9 — analyst queue
  "EVIDENCE_PENDING", // 10 — analyst queue
  "FINDING_GENERATED",       // 11 — analyst queue
  "APPROVAL_PENDING",   // 12 — manager queue
  "EXECUTION_READY",           // 13
  "OUTCOME_RECORDED",         // 14
  "NEW",             // 15 — analyst queue
  "FINDING_GENERATED",       // 16 — analyst queue
  "EVIDENCE_PENDING", // 17 — analyst queue
  "APPROVAL_PENDING",   // 18 — manager queue
  "DISPATCHED",           // 19
];

const BASE_AMOUNTS = [12500,8800,15200,6400,11000,9500,7800,13200,10600,8200,14800,9100,6900,12000,7500,11800,8400,10200,9800,13500];
const CONTRACT_BASE: Record<string, number> = { "BlueDart":8000,"Delhivery":7500,"FedEx":9200,"DTDC":6500,"Gati":7000 };

export const mockCases: Case[] = Array.from({ length: 20 }).map((_, i) => {
  const carrier = carriers[i % carriers.length];
  const amount  = BASE_AMOUNTS[i];
  const contract = CONTRACT_BASE[carrier] ?? 7500;
  const diff    = Math.max(300, amount - contract);
  return {
    id: `case_${(i + 1).toString().padStart(4, "0")}`,
    tenant_id: "amazon-india",
    state: FIXED_STATES[i],
    carrier,
    shipment_ref: `SHP-${20250000 + i}`,
    amount,
    currency: "INR",
    diff,
    confidence: parseFloat((0.72 + (i % 5) * 0.05).toFixed(2)),
    opened_at: T(i * 47),
    updated_at: T(i * 23),
  };
});

// SC-001 main case
mockCases[0] = {
  id: "case_0001",
  tenant_id: "amazon-india",
  state: "APPROVAL_PENDING",
  carrier: "BlueDart",
  shipment_ref: "HYD-WAR-20250115-001",
  amount: 12500,
  currency: "INR",
  diff: 4500,
  confidence: 0.96,
  opened_at: T(180),
  updated_at: T(15),
};

export const mockCanonicalInvoice: CanonicalInvoice = {
  id: "ci_7f3a91",
  tenant_id: "amazon-india",
  shipment_ref: "HYD-WAR-20250115-001",
  carrier: "BlueDart",
  amount: 12500,
  currency: "INR",
  canonical_hash: rndHash(),
  signature: rndHash(128),
  signed_at: T(178),
};

export const mockValidation: ValidationResult = {
  id: "val_001",
  case_id: "case_0001",
  outcome: "FAIL",
  diff: 4500,
  currency: "INR",
  reason: "Accessorial line item 'express_handling' is not authorised in contract.",
  invoice_amount: 12500,
  contract_amount: 8000,
  validated_at: T(175),
};

export const mockEvidenceBundle: EvidenceBundle = {
  id: "ev_001",
  case_id: "case_0001",
  merkle_root: rndHash(),
  item_count: 3,
  created_at: T(120),
  completeness_status: "COMPLETE",
  items: [
    { id: "ei_1", bundle_id: "ev_001", item_type: "BOL",        leaf_hash: rndHash(), added_at: T(120) },
    { id: "ei_2", bundle_id: "ev_001", item_type: "RATE_SHEET", leaf_hash: rndHash(), added_at: T(119) },
    { id: "ei_3", bundle_id: "ev_001", item_type: "INVOICE",    leaf_hash: rndHash(), added_at: T(118) },
  ],
};

export const mockFinding: Finding = {
  id: "find_001",
  case_id: "case_0001",
  confidence: 0.96,
  trace: {
    fuel_charge: { confidence: 1.00, weight: 0.50 },
    accessorial: { confidence: 0.92, weight: 0.50 },
  },
  finding_hash: rndHash(),
  created_at: T(90),
};

export const mockProposal: DecisionProposal = {
  id: "prop_001",
  case_id: "case_0001",
  action: "EXECUTE_CREDIT_MEMO",
  amount: 4500,
  currency: "INR",
  proposed_by: "user_analyst_01",
  proposed_at: T(45),
};

export const mockDecisions: GovernanceDecision[] = [
  {
    id: "dec_001",
    case_id: "case_0002",
    proposer_sub: "user_analyst_01",
    actor_sub: "user_manager_01",
    decision: "EXECUTION_READY",
    decision_hash: rndHash(),
    decided_at: T(220),
  },
];

export const mockTokens: GovernanceToken[] = [
  {
    id: "tok_001",
    case_id: "case_0002",
    tenant_id: "amazon-india",
    action: "EXECUTE_CREDIT_MEMO",
    amount: 4500,
    currency: "INR",
    tenant_binding: rndHash(),
    exp: new Date(NOW.getTime() + 24 * 3600 * 1000).toISOString(),
    status: "ACTIVE",
    signature: rndHash(128),
    key_id: "amazon-india-signing-2025-01",
    issued_at: T(210),
  },
];

export const mockEvents: CaseEvent[] = [
  { id: "ce_1", case_id: "case_0001", from_state: null,                  to_state: "NEW",             actor: "system", reason: "invoice_failed_validation", created_at: T(180) },
  { id: "ce_2", case_id: "case_0001", from_state: "NEW",              to_state: "EVIDENCE_PENDING", actor: "system", reason: "auto_progression",          created_at: T(178) },
  { id: "ce_3", case_id: "case_0001", from_state: "EVIDENCE_PENDING",  to_state: "FINDING_GENERATED",       actor: "system", reason: "evidence_complete",         created_at: T(120) },
  { id: "ce_4", case_id: "case_0001", from_state: "FINDING_GENERATED",        to_state: "APPROVAL_PENDING",   actor: "user_analyst_01", reason: "proposal_submitted", created_at: T(45) },
];

export const mockKafkaEvents: KafkaEvent[] = [
  { topic: "zoiko.source.record.received",   key: "case_0001", payload: { amount: 12500 }, published_at: T(180) },
  { topic: "zoiko.source.record.validated",  key: "case_0001", payload: { outcome: "FAIL", diff: 4500 }, published_at: T(175) },
  { topic: "zoiko.canonical.invoice.created",  key: "case_0001", payload: { canonical_hash: rndHash().slice(0, 18) }, published_at: T(172) },
  { topic: "zoiko.case.opened",        key: "case_0001", payload: { state: "NEW" }, published_at: T(170) },
  { topic: "zoiko.case.updated",       key: "case_0001", payload: { state: "EVIDENCE_PENDING" }, published_at: T(168) },
  { topic: "zoiko.evidence.bundled",   key: "case_0001", payload: { root: rndHash().slice(0, 18), items: 3 }, published_at: T(120) },
  { topic: "zoiko.finding.generated",    key: "case_0001", payload: { confidence: 0.96 }, published_at: T(90) },
  { topic: "zoiko.proposal.created",   key: "case_0001", payload: { amount: 4500 }, published_at: T(45) },
  { topic: "zoiko.case.updated",       key: "case_0001", payload: { state: "APPROVAL_PENDING" }, published_at: T(15) },
];

export const mockSourceRecords: SourceRecord[] = mockCases.slice(0, 6).map(c => ({
  id: `sr_${c.id}`,
  tenant_id: c.tenant_id,
  canonical_hash: rndHash(),
  signature: rndHash(128),
  key_id: "amazon-india-signing-2025-01",
  received_at: c.opened_at,
  payload_preview: { carrier: c.carrier, amount: c.amount, shipment: c.shipment_ref },
}));

export { rndHash };
