// Types matching the Zoiko backend DB schema (Phases 0-4)

// Case FSM states (spec §7.5 — aligned with implementation plan)
export type CaseState =
  | "NEW"               // Case opened after invoice validation
  | "EVIDENCE_PENDING"  // Evidence bundle being collected
  | "FINDING_GENERATED" // AI reasoned; ready for analyst proposal
  | "APPROVAL_PENDING"  // Analyst proposed; awaiting manager approval
  | "EXECUTION_READY"   // Manager approved; governance token issued (15-min TTL)
  | "DISPATCHED"        // 8-gate execution gateway passed; credit memo sent
  | "OUTCOME_RECORDED"  // Reconciliation complete; GL journal recorded
  | "CLOSED"            // ACR locked in WORM; case archived
  | "ABORTED";          // Rejected at any stage

export type ValidationOutcome = "PASS" | "FAIL";

export type TokenStatus = "ACTIVE" | "CONSUMED" | "EXPIRED" | "REVOKED";

export type VarianceStatus = "OPEN" | "RESOLVED" | "WAIVED";

export type VarianceType =
  | "AMOUNT_MISMATCH"
  | "CARRIER_MISMATCH"
  | "CURRENCY_MISMATCH"
  | "OVERCHARGE_DELTA"
  | "OTHER";

export interface Tenant {
  id: string;
  slug: string;
  name: string;
  created_at: string;
}

export interface SourceRecord {
  id: string;
  tenant_id: string;
  canonical_hash: string;
  signature: string;
  key_id: string;
  received_at: string;
  payload_preview?: Record<string, unknown>;
}

export interface ValidationResult {
  id: string;
  case_id: string;
  outcome: ValidationOutcome;
  diff: number;
  currency: string;
  reason: string;
  invoice_amount: number;
  contract_amount: number;
  validated_at: string;
}

export interface CanonicalInvoice {
  id: string;
  tenant_id: string;
  shipment_ref: string;
  carrier: string;
  amount: number;
  currency: string;
  canonical_hash: string;
  signature: string;
  signed_at: string;
}

export interface Case {
  id: string;
  tenant_id: string;
  state: CaseState;
  carrier: string;
  shipment_ref: string;
  amount: number;
  currency: string;
  diff: number;
  confidence?: number;
  opened_at: string;
  updated_at: string;
}

export interface CaseEvent {
  id: string;
  case_id: string;
  from_state: CaseState | null;
  to_state: CaseState;
  actor: string;
  reason: string;
  created_at: string;
}

export interface EvidenceItem {
  id: string;
  bundle_id: string;
  item_type: "BOL" | "RATE_SHEET" | "INVOICE" | "EMAIL" | "OTHER";
  leaf_hash: string;
  added_at: string;
}

export interface EvidenceBundle {
  id: string;
  case_id: string;
  merkle_root: string;
  item_count: number;
  created_at: string;
  completeness_status: "INCOMPLETE" | "COMPLETE";
  items?: EvidenceItem[];
}

export interface Finding {
  id: string;
  case_id: string;
  confidence: number;
  trace: Record<string, { confidence: number; weight: number }>;
  finding_hash: string;
  created_at: string;
  risk_level?:    "HIGH" | "MEDIUM" | "LOW";
  ai_confidence?: number;
  ai_reasoning?:  string;
}

export interface DecisionProposal {
  id: string;
  case_id: string;
  action: "EXECUTE_CREDIT_MEMO" | "DISMISS" | "ESCALATE";
  amount: number;
  currency: string;
  proposed_by: string;
  proposed_at: string;
}

export interface ApprovalTask {
  id: string;
  case_id: string;
  proposer_sub: string;
  status: "PENDING" | "APPROVED" | "REJECTED";
  created_at: string;
}

export interface GovernanceDecision {
  id: string;
  case_id: string;
  proposer_sub: string;
  actor_sub: string;
  decision: "EXECUTION_READY" | "ABORTED";
  decision_hash: string;
  decided_at: string;
}

export interface GovernanceToken {
  id: string;
  case_id: string;
  tenant_id: string;
  action: string;
  amount: number;
  currency: string;
  tenant_binding: string;
  exp: string;
  status: TokenStatus;
  signature: string;
  key_id: string;
  issued_at: string;
}

export interface VarianceRecord {
  id: string;
  case_id: string;
  variance_type: VarianceType;
  expected_value: number;
  actual_value: number;
  delta: number;
  status: VarianceStatus;
  resolved_by?: string;
  resolved_at?: string;
  created_at: string;
}

export interface ACRBundle {
  id: string;
  case_id: string;
  tenant_id: string;
  merkle_root: string;
  acr_hash: string;
  signature: string;
  kid: string;
  issued_at: string;
  is_locked: boolean;
  artifact_count?: number;
}

export interface ExecutionResult {
  envelope_id: string;
  case_id: string;
  token_id: string;
  gates_passed: number;
  status: string;
  dispatched_at: string;
}

export interface KafkaEvent {
  topic: string;
  key: string;
  payload: Record<string, unknown>;
  published_at: string;
}

export interface DashboardStats {
  total_cases: number;
  pending_approval: number;
  approved: number;
  total_recovered: number;
  avg_confidence: number;
}
