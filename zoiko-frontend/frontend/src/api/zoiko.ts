import { api, api3, api4, apiClaim, apiClaim3, apiClaim4, apiException, apiException4, apiScore, apiScore4, apiAcc, apiAcc4, USE_MOCK } from "./client";
import * as mocks from "@/mocks/fixtures";
import type {
  Case, Claim, CanonicalInvoice, ValidationResult, EvidenceBundle, Finding,
  DecisionProposal, GovernanceToken, GovernanceDecision, CaseEvent, NegotiationRound,
  KafkaEvent, DashboardStats, SourceRecord, VarianceRecord, ACRBundle,
  ExecutionResult, RecoveryProof,
  ExpectedRecovery, RecoveryInstrument, RecoveryMatch, RecoveryException, ReconcileResult,
  LegalHold, RetentionPolicy, RetentionAssignment,
  CryptoShredRequest, CryptoShredVerification,
  RestoreJob, RestoreVerification,
  ArchiveJob, PurgeJob,
  ObservabilityMetrics, ObservabilityAlert,
  ScorecardPeriod,
  ShipmentException,
} from "@/types";

// Simulates network latency for mock mode so loading states are visible
const delay = (ms = 250) => new Promise(r => setTimeout(r, ms));

// ── Auth types ────────────────────────────────────────────────────────────────
export interface LoginResponse {
  token:      string;
  tenant_id:  string;
  role:       string;
  full_name:  string;
  email:      string;
  expires_in: number;
}

export interface RegisterRequest {
  email:     string;
  password:  string;
  full_name: string;
  role:      "analyst" | "manager" | "admin";
}

export interface UserItem {
  user_id:    string;
  email:      string;
  full_name:  string;
  role:       string;
  is_active:  boolean;
  created_at: string;
}

export interface ApiKeyItem {
  id:           string;
  name:         string;
  key_prefix:   string;
  scopes:       string;
  created_at:   string;
  last_used_at: string | null;
  revoked:      boolean;
}

export interface CreateApiKeyResponse {
  id:         string;
  name:       string;
  key:        string;
  key_prefix: string;
  scopes:     string;
  created_at: string;
}

export interface NotificationSettings {
  case_opened_email:         boolean;
  overcharge_detected_email: boolean;
  approval_needed_email:     boolean;
  recovery_executed_email:   boolean;
}

export interface UsageSummary {
  plan:             string;
  member_since:     string;
  total_cases:      number;
  cases_this_month: number;
  total_recovered:  number;
  active_users:     number;
}

export const zoikoApi = {
  // ---------- Auth ----------
  async login(email: string, password: string): Promise<LoginResponse> {
    const { data } = await api.post<LoginResponse>("/auth/login", { email, password });
    return data;
  },

  async registerUser(req: RegisterRequest): Promise<UserItem> {
    const { data } = await api.post<UserItem>("/auth/register", req);
    return data;
  },

  async listUsers(): Promise<UserItem[]> {
    const { data } = await api.get<{ users: UserItem[] }>("/auth/users");
    return data.users;
  },

  // ---------- API Keys ----------
  async listApiKeys(): Promise<ApiKeyItem[]> {
    const { data } = await api.get<{ api_keys: ApiKeyItem[] }>("/api-keys");
    return data.api_keys;
  },

  async createApiKey(name: string, scopes = "read:*"): Promise<CreateApiKeyResponse> {
    const { data } = await api.post<CreateApiKeyResponse>("/api-keys", { name, scopes });
    return data;
  },

  async revokeApiKey(id: string): Promise<void> {
    await api.delete(`/api-keys/${id}`);
  },

  // ---------- Notification Settings ----------
  async getNotificationSettings(): Promise<NotificationSettings> {
    const { data } = await api.get<NotificationSettings>("/settings/notifications");
    return data;
  },

  async updateNotificationSettings(settings: NotificationSettings): Promise<NotificationSettings> {
    const { data } = await api.put<NotificationSettings>("/settings/notifications", settings);
    return data;
  },

  // ---------- Billing / Usage ----------
  async getUsageSummary(): Promise<UsageSummary> {
    const { data } = await api.get<UsageSummary>("/billing/usage");
    return data;
  },

  // ---------- Dashboard ----------
  async getStats(): Promise<DashboardStats> {
    if (USE_MOCK) { await delay(); return mocks.mockStats; }
    const { data } = await api.get<DashboardStats>("/stats");
    return data;
  },

  // ---------- Cases ----------
  async listCases(filters?: { state?: string; page?: number; page_size?: number }): Promise<Case[]> {
    if (USE_MOCK) {
      await delay();
      return filters?.state
        ? mocks.mockCases.filter(c => c.state === filters.state)
        : mocks.mockCases;
    }
    const { data } = await api.get<{ cases: Case[]; total: number; page: number; pages: number } | Case[]>(
      "/cases", { params: filters }
    );
    // Handle both paginated response and legacy array response
    return Array.isArray(data) ? data : data.cases;
  },

  async listCasesPaged(filters?: { state?: string; page?: number; page_size?: number }): Promise<{ cases: Case[]; total: number; page: number; pages: number }> {
    if (USE_MOCK) {
      await delay();
      const cases = filters?.state ? mocks.mockCases.filter(c => c.state === filters.state) : mocks.mockCases;
      return { cases, total: cases.length, page: 1, pages: 1 };
    }
    const { data } = await api.get<{ cases: Case[]; total: number; page: number; pages: number }>("/cases", { params: filters });
    return data;
  },

  async getCase(id: string): Promise<Case> {
    if (USE_MOCK) {
      await delay();
      const c = mocks.mockCases.find(x => x.id === id);
      if (!c) throw new Error("Case not found");
      return c;
    }
    const { data } = await api.get<Case>(`/cases/${id}`);
    return data;
  },

  async getCaseEvents(caseId: string): Promise<CaseEvent[]> {
    if (USE_MOCK) {
      await delay();
      return mocks.mockEvents.filter(e => e.case_id === caseId);
    }
    const { data } = await api.get<CaseEvent[]>(`/cases/${caseId}/events`);
    return data;
  },

  async createCase(payload: { invoice_number?: string; invoice_date?: string; transport_mode?: string; equipment_type?: string; shipper_reference?: string; charge_lines?: {description:string;amount:number;type:string}[]; carrier: string; route: string; amount: number; currency: string }): Promise<Case> {
    if (USE_MOCK) {
      await delay(500);
      const CONTRACT_BASE: Record<string, number> = {
        "BlueDart": 8000, "Delhivery": 7500, "FedEx India": 9200,
        "DTDC": 6500, "Ekart": 7000, "UPS India": 10500, "V Express": 50000, "Other": 7000,
      };
      const contractAmt = CONTRACT_BASE[payload.carrier] ?? Math.round(payload.amount * 0.72);
      const diff = Math.max(200, payload.amount - contractAmt);
      const confidence = parseFloat((0.72 + Math.random() * 0.25).toFixed(2));
      const now = new Date().toISOString();
      const newCase: Case = {
        id: `case_${Date.now().toString().slice(-6)}`,
        tenant_id: "amazon-india",
        carrier: payload.carrier,
        shipment_ref: payload.route,
        amount: payload.amount,
        currency: payload.currency,
        diff,
        confidence,
        state: "FINDING_GENERATED",
        opened_at: now,
        updated_at: now,
      };
      mocks.mockCases.unshift(newCase);
      return newCase;
    }
    // Step 1: POST /cases/submit-async → returns job_id immediately (<1s).
    // This replaces the old 25s blocking call that NAT/firewalls would drop.
    const { data: job } = await api.post<{ job_id: string }>(
      "/cases/submit-async", payload, { timeout: 10000 }
    );
    // Step 2: Poll every 2s until the pipeline finishes (max 90s).
    for (let i = 0; i < 45; i++) {
      await new Promise(r => setTimeout(r, 2000));
      const { data: s } = await api.get<{ status: string; case: Case | null; error: string | null }>(
        `/cases/submit-status/${job.job_id}`, { timeout: 8000 }
      );
      if (s.status === "done" && s.case) return s.case;
      if (s.status === "error") throw new Error(s.error || "Pipeline failed");
    }
    throw new Error("Timed out waiting for case (90s)");
  },

  // ---------- Claims (SC-002) ----------
  // SC-002 is a fully separate backend (backend/slices/sc-002-carrier-claim/spine/),
  // not a route on the SC-001 backend — every claims call below uses apiClaim*
  // (port 8010/8011/8012), never api/api3/api4 (SC-001, port 8000/8001/8002).
  async listClaimsPaged(filters?: { state?: string; page?: number; page_size?: number }): Promise<{ claims: Claim[]; total: number; page: number; pages: number }> {
    if (USE_MOCK) { await delay(); return { claims: [], total: 0, page: 1, pages: 1 }; }
    const { data } = await apiClaim.get<{ claims: Claim[]; total: number; page: number; pages: number }>("/claims", { params: filters });
    return data;
  },

  async getClaim(id: string): Promise<Claim> {
    if (USE_MOCK) { await delay(); throw new Error("Not available in mock mode"); }
    const { data } = await apiClaim.get<Claim>(`/claims/${id}`);
    return data;
  },

  async getClaimLines(id: string): Promise<{ id: string; line_number: number; description: string; claimed_amount: number; currency: string; created_at: string }[]> {
    if (USE_MOCK) { await delay(); return []; }
    const { data } = await apiClaim.get(`/claims/${id}/lines`);
    return data;
  },

  async negotiateClaim(id: string, body: { action: "COUNTER" | "ACCEPT" | "PARTIALLY_ACCEPT" | "REJECT"; approved_amount?: number; note?: string }): Promise<{ case_id: string; negotiation_status: string; approved_amount: number | null }> {
    if (USE_MOCK) { await delay(); throw new Error("Not available in mock mode"); }
    const { data } = await apiClaim.post(`/claims/${id}/negotiate`, body);
    return data;
  },

  async createClaim(payload: {
    carrier: string; claim_type: string; claimed_amount: number; currency: string;
    claim_reference?: string; description?: string; related_invoice_number?: string;
    awb_number?: string; incident_date?: string;
    origin_location?: string; destination_location?: string;
    lines?: { description: string; claimed_amount: number }[];
  }): Promise<Claim> {
    if (USE_MOCK) {
      await delay(500);
      throw new Error("Claim submission is not available in mock mode — set VITE_USE_MOCK=false");
    }
    // Same async submit + poll pattern as createCase() — avoids the
    // ~15s blocking call that NAT/proxy connections drop.
    const { data: job } = await apiClaim.post<{ job_id: string }>(
      "/claims/submit-async", payload, { timeout: 10000 }
    );
    for (let i = 0; i < 45; i++) {
      await new Promise(r => setTimeout(r, 2000));
      const { data: s } = await apiClaim.get<{ status: string; case: Claim | null; error: string | null }>(
        `/claims/submit-status/${job.job_id}`, { timeout: 8000 }
      );
      if (s.status === "done" && s.case) return s.case;
      if (s.status === "error") throw new Error(s.error || "Pipeline failed");
    }
    throw new Error("Timed out waiting for claim (90s)");
  },

  // ---------- Claims (SC-002) — governance/execution pipeline ----------
  // Mirrors the generic case methods below (getCaseEvents, getEvidence, getFinding,
  // getProposal, proposeRecovery, approveDecision, getTokenForCase, executeRecovery,
  // getAcr, downloadAcr) but routed to SC-002's own gateway/governance/execution —
  // a claim id only exists in SC-002's case_type=CARRIER_CLAIM branch.
  async getClaimEvents(claimId: string): Promise<CaseEvent[]> {
    if (USE_MOCK) { await delay(); return []; }
    const { data } = await apiClaim.get<CaseEvent[]>(`/cases/${claimId}/events`);
    return data;
  },

  async getClaimNegotiationHistory(claimId: string): Promise<NegotiationRound[]> {
    if (USE_MOCK) { await delay(); return []; }
    const { data } = await apiClaim.get<NegotiationRound[]>(`/claims/${claimId}/negotiation-history`);
    return data;
  },

  async getClaimEvidence(claimId: string): Promise<EvidenceBundle> {
    if (USE_MOCK) { await delay(); return mocks.mockEvidenceBundle; }
    const { data } = await apiClaim.get<EvidenceBundle>(`/cases/${claimId}/evidence`);
    return data;
  },

  async getClaimFinding(claimId: string): Promise<Finding> {
    if (USE_MOCK) { await delay(); return mocks.mockFinding; }
    const { data } = await apiClaim.get<Finding>(`/cases/${claimId}/finding`);
    return data;
  },

  async getClaimProposal(claimId: string): Promise<DecisionProposal> {
    if (USE_MOCK) { await delay(); return mocks.mockProposal; }
    const { data } = await apiClaim.get<DecisionProposal>(`/cases/${claimId}/proposal`);
    return data;
  },

  async proposeClaimSettlement(claimId: string, payload: { action: string; amount: number; currency: string }): Promise<DecisionProposal> {
    if (USE_MOCK) { await delay(500); throw new Error("Not available in mock mode"); }
    const { data } = await apiClaim.post<DecisionProposal>(`/cases/${claimId}/proposal`, payload);
    return data;
  },

  async approveClaimDecision(claimId: string, payload: { decision: "EXECUTION_READY" | "ABORTED"; note?: string }): Promise<GovernanceDecision> {
    if (USE_MOCK) { await delay(700); throw new Error("Not available in mock mode"); }
    const { data } = await apiClaim.post<GovernanceDecision>(`/cases/${claimId}/decide`, payload);
    return data;
  },

  async getClaimToken(claimId: string): Promise<GovernanceToken | null> {
    if (USE_MOCK) { await delay(); return null; }
    const { data } = await apiClaim.get<GovernanceToken | null>(`/cases/${claimId}/token`);
    return data;
  },

  async executeClaimRecovery(tokenId: string, claimId: string, amount: number, currency: string): Promise<ExecutionResult> {
    if (USE_MOCK) { await delay(1200); throw new Error("Not available in mock mode"); }
    const { data } = await apiClaim4.post<ExecutionResult>("/execute", { token_id: tokenId, case_id: claimId, amount, currency });
    return data;
  },

  async getClaimAcr(claimId: string): Promise<ACRBundle | null> {
    if (USE_MOCK) { await delay(); return null; }
    try {
      const { data } = await apiClaim.get<ACRBundle>(`/cases/${claimId}/acr`);
      return data;
    } catch {
      return null;
    }
  },

  async downloadClaimAcr(claimId: string): Promise<Blob> {
    if (USE_MOCK) { await delay(800); return new Blob(["mock acr zip"], { type: "application/zip" }); }
    const response = await apiClaim.get(`/cases/${claimId}/acr/download`, { responseType: "blob" });
    return response.data as Blob;
  },

  // ---------- Phase 2 artifacts ----------
  async getSourceRecords(): Promise<SourceRecord[]> {
    if (USE_MOCK) { await delay(); return mocks.mockSourceRecords; }
    const { data } = await api.get<SourceRecord[]>("/ingestion/source-records");
    return data;
  },

  async getValidationForCase(caseId: string): Promise<ValidationResult> {
    if (USE_MOCK) { await delay(); return mocks.mockValidation; }
    const { data } = await api.get<ValidationResult>(`/cases/${caseId}/validation`);
    return data;
  },

  async getCanonicalInvoice(caseId: string): Promise<CanonicalInvoice> {
    if (USE_MOCK) { await delay(); return mocks.mockCanonicalInvoice; }
    const { data } = await api.get<CanonicalInvoice>(`/cases/${caseId}/canonical-invoice`);
    return data;
  },

  // ---------- Phase 3 artifacts ----------
  async getEvidence(caseId: string): Promise<EvidenceBundle> {
    if (USE_MOCK) { await delay(); return mocks.mockEvidenceBundle; }
    const { data } = await api.get<EvidenceBundle>(`/cases/${caseId}/evidence`);
    return data;
  },

  async sealBundle(caseId: string): Promise<{ bundle_id: string; completeness_status: string }> {
    if (USE_MOCK) { await delay(400); return { bundle_id: "bnd_mock", completeness_status: "COMPLETE" }; }
    const { data } = await api3.post(`/evidence/${caseId}/bundle/seal`);
    return data;
  },

  async getFinding(caseId: string): Promise<Finding> {
    if (USE_MOCK) { await delay(); return mocks.mockFinding; }
    const { data } = await api.get<Finding>(`/cases/${caseId}/finding`);
    return data;
  },

  async getProposal(caseId: string): Promise<DecisionProposal> {
    if (USE_MOCK) { await delay(); return mocks.mockProposal; }
    const { data } = await api.get<DecisionProposal>(`/cases/${caseId}/proposal`);
    return data;
  },

  async proposeRecovery(caseId: string, payload: { action: string; amount: number; currency: string }): Promise<DecisionProposal> {
    if (USE_MOCK) {
      await delay(500);
      const c = mocks.mockCases.find(x => x.id === caseId);
      if (c) { c.state = "APPROVAL_PENDING"; c.updated_at = new Date().toISOString(); }
      return { ...mocks.mockProposal, case_id: caseId, ...payload } as DecisionProposal;
    }
    const { data } = await api.post<DecisionProposal>(`/cases/${caseId}/proposal`, payload);
    return data;
  },

  async approveDecision(caseId: string, payload: { decision: "EXECUTION_READY" | "ABORTED"; note?: string }): Promise<GovernanceDecision> {
    if (USE_MOCK) {
      await delay(700);
      const c = mocks.mockCases.find(x => x.id === caseId);
      if (c) {
        c.state = payload.decision === "EXECUTION_READY" ? "EXECUTION_READY" : "ABORTED";
        c.updated_at = new Date().toISOString();
      }
      if (payload.decision === "EXECUTION_READY") {
        const existing = mocks.mockTokens.find(t => t.case_id === caseId);
        if (!existing) {
          mocks.mockTokens.push({
            id: `tok_${Date.now()}`, case_id: caseId, tenant_id: "amazon-india",
            action: "EXECUTE_CREDIT_MEMO", amount: c?.diff ?? 4500, currency: c?.currency ?? "INR",
            tenant_binding: mocks.rndHash(), exp: new Date(Date.now() + 15 * 60_000).toISOString(),
            status: "ACTIVE", signature: mocks.rndHash(128), key_id: "amazon-india-signing-2025-01",
            issued_at: new Date().toISOString(),
          });
        }
      }
      return {
        id: `dec_${Date.now()}`, case_id: caseId, proposer_sub: "user_analyst_01",
        actor_sub: "user_manager_01", decision: payload.decision,
        decision_hash: mocks.rndHash(), decided_at: new Date().toISOString(),
      };
    }
    const { data } = await api.post<GovernanceDecision>(`/cases/${caseId}/decide`, payload);
    return data;
  },

  async listTokens(filters?: { status?: string }): Promise<GovernanceToken[]> {
    if (USE_MOCK) {
      await delay();
      return filters?.status ? mocks.mockTokens.filter(t => t.status === filters.status) : mocks.mockTokens;
    }
    const { data } = await api.get<GovernanceToken[]>("/tokens", { params: filters });
    return data;
  },

  async getTokenForCase(caseId: string): Promise<GovernanceToken | null> {
    if (USE_MOCK) { await delay(); return mocks.mockTokens.find(t => t.case_id === caseId) ?? null; }
    const { data } = await api.get<GovernanceToken | null>(`/cases/${caseId}/token`);
    return data;
  },

  // ---------- Phase 4 — Execution ----------
  async executeRecovery(tokenId: string, caseId: string, amount: number, currency: string): Promise<ExecutionResult> {
    if (USE_MOCK) {
      await delay(1200);
      const c = mocks.mockCases.find(x => x.id === caseId);
      if (c) { c.state = "DISPATCHED"; c.updated_at = new Date().toISOString(); }
      return { envelope_id: `env_${Date.now()}`, case_id: caseId, token_id: tokenId, gates_passed: 8, status: "DISPATCHED", dispatched_at: new Date().toISOString() };
    }
    // Uses Phase 2 gateway (port 8000) — no separate Phase 4 service needed
    const { data } = await api.post<ExecutionResult>("/execute", { token_id: tokenId, case_id: caseId, amount, currency });
    return data;
  },

  // ---------- Phase 4 — Variances ----------
  async listVariances(caseId: string): Promise<VarianceRecord[]> {
    if (USE_MOCK) { await delay(); return []; }
    const { data } = await api4.get<VarianceRecord[]>(`/cases/${caseId}/variances`);
    return data;
  },

  async resolveVariance(caseId: string, varianceId: string, action: "RESOLVE" | "WAIVE"): Promise<VarianceRecord> {
    if (USE_MOCK) { await delay(300); return {} as VarianceRecord; }
    const { data } = await api4.patch<VarianceRecord>(`/cases/${caseId}/variances/${varianceId}/resolve`, { action });
    return data;
  },

  // ---------- Phase 4 — ACR ----------
  async getAcr(caseId: string): Promise<ACRBundle | null> {
    if (USE_MOCK) { await delay(); return null; }
    try {
      const { data } = await api.get<ACRBundle>(`/cases/${caseId}/acr`);
      return data;
    } catch {
      return null;
    }
  },

  async downloadAcr(caseId: string): Promise<Blob> {
    if (USE_MOCK) { await delay(800); return new Blob(["mock acr zip"], { type: "application/zip" }); }
    const response = await api.get(`/cases/${caseId}/acr/download`, { responseType: "blob" });
    return response.data as Blob;
  },

  // ---------- Phase 6 — Recovery ----------
  async getLatestRecoveryProof(caseId: string): Promise<RecoveryProof | null> {
    if (USE_MOCK) { await delay(); return null; }
    try {
      const { data } = await api4.get<RecoveryProof>(`/recovery/proofs:latest`, { params: { case_id: caseId } });
      return data;
    } catch {
      return null;
    }
  },

  async listRecoveryProofsByCase(caseId: string): Promise<RecoveryProof[]> {
    if (USE_MOCK) { await delay(); return []; }
    const { data } = await api4.get<RecoveryProof[]>(`/recovery/proofs:by-case`, { params: { case_id: caseId } });
    return data;
  },

  async generateRecoveryProof(caseId: string): Promise<RecoveryProof> {
    if (USE_MOCK) { await delay(800); throw new Error("Not available in mock mode"); }
    const { data } = await api4.post<RecoveryProof>("/recovery/proofs", { case_id: caseId });
    return data;
  },

  async listExpectedRecoveriesByCase(caseId: string): Promise<ExpectedRecovery[]> {
    if (USE_MOCK) { await delay(); return []; }
    const { data } = await api4.get<ExpectedRecovery[]>("/recovery/expected:by-case", { params: { case_id: caseId } });
    return data;
  },

  async createExpectedRecovery(payload: {
    case_id: string;
    expected_amount: number;
    currency?: string;
    expected_recovery_method?: string;
    counterparty_type?: string;
    counterparty_id?: string;
    expected_external_invoice_ref?: string;
    authorization_decision_id?: string;
  }): Promise<ExpectedRecovery> {
    if (USE_MOCK) { await delay(500); throw new Error("Not available in mock mode"); }
    const { data } = await api4.post<ExpectedRecovery>("/recovery/expected", payload);
    return data;
  },

  async listRecoveryInstrumentsByCase(caseId: string): Promise<RecoveryInstrument[]> {
    if (USE_MOCK) { await delay(); return []; }
    const { data } = await api4.get<RecoveryInstrument[]>("/recovery/instruments:by-case", { params: { case_id: caseId } });
    return data;
  },

  async createRecoveryInstrument(payload: {
    instrument_type: string;
    instrument_amount: number;
    currency?: string;
    counterparty_type?: string;
    counterparty_id?: string;
    related_case_id?: string;
    external_reference?: string;
    related_external_invoice_ref?: string;
    instrument_date?: string;
  }): Promise<RecoveryInstrument> {
    if (USE_MOCK) { await delay(500); throw new Error("Not available in mock mode"); }
    const { data } = await api4.post<RecoveryInstrument>("/recovery/instruments", payload);
    return data;
  },

  async listRecoveryMatchesByCase(caseId: string): Promise<RecoveryMatch[]> {
    if (USE_MOCK) { await delay(); return []; }
    const { data } = await api4.get<RecoveryMatch[]>("/recovery/matches:by-case", { params: { case_id: caseId } });
    return data;
  },

  async createRecoveryMatch(expectedRecoveryId: string): Promise<RecoveryMatch> {
    if (USE_MOCK) { await delay(500); throw new Error("Not available in mock mode"); }
    const { data } = await api4.post<RecoveryMatch>("/recovery/match", { expected_recovery_id: expectedRecoveryId });
    return data;
  },

  async reverseRecoveryMatch(matchId: string, reason = ""): Promise<RecoveryMatch> {
    if (USE_MOCK) { await delay(500); throw new Error("Not available in mock mode"); }
    const { data } = await api4.post<RecoveryMatch>(`/recovery/matches/${matchId}/reverse`, { reason });
    return data;
  },

  async listRecoveryExceptions(caseId?: string, stuckAfterDays = 7): Promise<RecoveryException[]> {
    if (USE_MOCK) { await delay(); return []; }
    const { data } = await api4.get<RecoveryException[]>("/recovery/exceptions", {
      params: { case_id: caseId, stuck_after_days: stuckAfterDays },
    });
    return data;
  },

  // ---------- SC-002 Claim Recovery (apiClaim4 = port 8011) ----------
  // These mirror the Phase 6 methods above but route to the SC-002 execution
  // gateway, not the SC-001 one. ClaimDetail.tsx MUST use these, not the api4 variants.
  async listClaimExpectedRecoveries(caseId: string): Promise<ExpectedRecovery[]> {
    if (USE_MOCK) { await delay(); return []; }
    try {
      const { data } = await apiClaim4.get<ExpectedRecovery[]>("/recovery/expected:by-case", { params: { case_id: caseId } });
      return data;
    } catch { return []; }
  },

  async listClaimRecoveryInstruments(caseId: string): Promise<RecoveryInstrument[]> {
    if (USE_MOCK) { await delay(); return []; }
    try {
      const { data } = await apiClaim4.get<RecoveryInstrument[]>("/recovery/instruments:by-case", { params: { case_id: caseId } });
      return data;
    } catch { return []; }
  },

  async listClaimRecoveryMatches(caseId: string): Promise<RecoveryMatch[]> {
    if (USE_MOCK) { await delay(); return []; }
    try {
      const { data } = await apiClaim4.get<RecoveryMatch[]>("/recovery/matches:by-case", { params: { case_id: caseId } });
      return data;
    } catch { return []; }
  },

  async getLatestClaimRecoveryProof(caseId: string): Promise<RecoveryProof | null> {
    if (USE_MOCK) { await delay(); return null; }
    try {
      const { data } = await apiClaim4.get<RecoveryProof>("/recovery/proofs:latest", { params: { case_id: caseId } });
      return data;
    } catch { return null; }
  },

  async generateClaimRecoveryProof(caseId: string): Promise<RecoveryProof> {
    if (USE_MOCK) { await delay(800); throw new Error("Not available in mock mode"); }
    const { data } = await apiClaim4.post<RecoveryProof>("/recovery/proofs", { case_id: caseId });
    return data;
  },

  async confirmClaimPayment(recoveryInstrumentId: string, paymentRef: string): Promise<RecoveryInstrument> {
    if (USE_MOCK) { await delay(500); throw new Error("Not available in mock mode"); }
    const { data } = await apiClaim4.post<RecoveryInstrument>("/recovery/payment-confirm", {
      recovery_instrument_id: recoveryInstrumentId,
      payment_ref: paymentRef,
    });
    return data;
  },

  // ---------- Phase 4 — Reconciliation ----------
  async reconcileEnvelope(envelopeId: string, actorSub: string): Promise<ReconcileResult> {
    if (USE_MOCK) { await delay(800); throw new Error("Not available in mock mode"); }
    const { data } = await api4.post<ReconcileResult>("/reconcile", { envelope_id: envelopeId, actor_sub: actorSub });
    return data;
  },

  // ---------- Contract rates ----------
  async listContractRates(): Promise<{ id: string; carrier: string; rate_type: string; rate_value: number; currency: string; effective_on: string; expires_on: string | null }[]> {
    if (USE_MOCK) {
      await delay();
      return [
        { id: "cr1", carrier: "BlueDart",   rate_type: "FUEL_CHARGE", rate_value: 8000,  currency: "INR", effective_on: "2025-01-01", expires_on: null },
        { id: "cr2", carrier: "Delhivery",  rate_type: "FUEL_CHARGE", rate_value: 7500,  currency: "INR", effective_on: "2025-01-01", expires_on: null },
        { id: "cr3", carrier: "FedEx",      rate_type: "FUEL_CHARGE", rate_value: 9200,  currency: "INR", effective_on: "2025-01-01", expires_on: null },
        { id: "cr4", carrier: "DTDC",       rate_type: "FUEL_CHARGE", rate_value: 6500,  currency: "INR", effective_on: "2025-01-01", expires_on: "2025-12-31" },
        { id: "cr5", carrier: "Ekart",      rate_type: "FUEL_CHARGE", rate_value: 7000,  currency: "INR", effective_on: "2025-01-01", expires_on: null },
      ];
    }
    const { data } = await api.get("/contract-rates");
    return data;
  },

  async createContractRate(payload: {
    carrier_id:   string;
    rate_type:    string;
    rate_value:   number;
    currency:     string;
    effective_on: string;
    expires_on?:  string;
  }): Promise<{ id: string }> {
    if (USE_MOCK) { await delay(400); return { id: `cr_${Date.now()}` }; }
    const { data } = await api.post("/contract-rates", payload);
    return data;
  },

  async deleteContractRate(id: string): Promise<void> {
    if (USE_MOCK) { await delay(300); return; }
    await api.delete(`/contract-rates/${id}`);
  },

  // ---------- Phase 1 — security substrate ----------
  async listKafkaEvents(): Promise<KafkaEvent[]> {
    if (USE_MOCK) { await delay(); return mocks.mockKafkaEvents; }
    const { data } = await api.get<KafkaEvent[]>("/kafka/events");
    return data;
  },

  // ---------- Admin ----------
  async getDbStats(): Promise<{ table: string; rows: number }[]> {
    if (USE_MOCK) { await delay(); return []; }
    const { data } = await api.get<{ table: string; rows: number }[]>("/admin/db-stats");
    return data;
  },

  // ---------- Profile ----------
  async getProfile(): Promise<{ full_name: string; email: string; role: string; title: string; is_active: boolean; created_at: string }> {
    const { data } = await api.get("/auth/me");
    return data;
  },
  async updateProfile(payload: { title?: string; full_name?: string }): Promise<void> {
    await api.put("/auth/me", payload);
  },

  // ---------- Tenant info ----------
  async getTenant(): Promise<{ display_name: string; slug: string; address: string; city: string; state: string; pincode: string; phone: string; email: string; status: string }> {
    const { data } = await api.get("/auth/tenant");
    return data;
  },
  async updateTenant(payload: { address?: string; city?: string; state?: string; pincode?: string; phone?: string; email?: string }): Promise<void> {
    await api.put("/auth/tenant", payload);
  },

  // ---------- Carriers ----------
  async listCarriers(): Promise<CarrierItem[]> {
    const { data } = await api.get<CarrierItem[]>("/carriers");
    return data;
  },
  async createCarrier(payload: { name: string; email?: string; address?: string; contact_person?: string; contact_phone?: string; cc_emails?: string }): Promise<{ id: string; name: string }> {
    const { data } = await api.post("/carriers", payload);
    return data;
  },
  async updateCarrier(id: string, payload: { name?: string; email?: string; address?: string; contact_person?: string; contact_phone?: string; cc_emails?: string }): Promise<void> {
    await api.put(`/carriers/${id}`, payload);
  },
  async deleteCarrier(id: string): Promise<void> {
    await api.delete(`/carriers/${id}`);
  },

  // ---------- Tenant management ----------
  async listTenants(): Promise<TenantItem[]> {
    if (USE_MOCK) { await delay(); return []; }
    const { data } = await api.get<{ tenants: TenantItem[]; total: number }>("/admin/tenants");
    return data.tenants;
  },

  async createTenant(req: TenantCreateRequest): Promise<TenantCreateResponse> {
    if (USE_MOCK) {
      await delay(600);
      return { tenant_id: `t_${Date.now()}`, display_name: req.display_name, slug: req.slug,
               status: "ACTIVE", admin_user_id: `u_${Date.now()}`, admin_email: req.admin_email,
               created_at: new Date().toISOString() };
    }
    const { data } = await api.post<TenantCreateResponse>("/admin/tenants", req);
    return data;
  },

  // ── C07 — Observability ──────────────────────────────────────────────────────
  async getObservabilityMetrics(): Promise<ObservabilityMetrics> {
    const { data } = await api.get<ObservabilityMetrics>("/data/observability/metrics");
    return data;
  },

  async getObservabilityAlerts(): Promise<ObservabilityAlert[]> {
    const { data } = await api.get<ObservabilityAlert[]>("/data/observability/alerts");
    return data;
  },

  // ── C07 — Legal Holds ────────────────────────────────────────────────────────
  async createLegalHold(payload: { hold_scope: string; scope_id: string; reason_code: string; approved_by?: string }): Promise<LegalHold> {
    const { data } = await api.post<LegalHold>("/legal-holds", payload);
    return data;
  },

  async getLegalHold(id: string): Promise<LegalHold> {
    const { data } = await api.get<LegalHold>(`/legal-holds/${id}`);
    return data;
  },

  async releaseLegalHold(id: string, released_by: string): Promise<LegalHold> {
    const { data } = await api.post<LegalHold>(`/legal-holds/${id}/release`, { released_by });
    return data;
  },

  async legalHoldsByScope(scope_id: string): Promise<LegalHold[]> {
    const { data } = await api.get<LegalHold[]>("/legal-holds:by-scope", { params: { scope_id } });
    return data;
  },

  // ── C07 — Retention ─────────────────────────────────────────────────────────
  async createRetentionPolicy(payload: { policy_name: string; data_class: string; retention_class: string; retention_days: number; archive_after_days?: number; purge_after_days?: number }): Promise<RetentionPolicy> {
    const { data } = await api.post<RetentionPolicy>("/data/retention/policies", payload);
    return data;
  },

  async getRetentionPolicy(id: string): Promise<RetentionPolicy> {
    const { data } = await api.get<RetentionPolicy>(`/data/retention/policies/${id}`);
    return data;
  },

  async assignRetention(payload: { record_type: string; record_id: string; policy_id: string }): Promise<RetentionAssignment> {
    const { data } = await api.post<RetentionAssignment>("/data/retention/assign", payload);
    return data;
  },

  async retentionByRecord(record_id: string): Promise<RetentionAssignment | null> {
    try {
      const { data } = await api.get<RetentionAssignment>("/data/retention:by-record", { params: { record_id } });
      return data;
    } catch { return null; }
  },

  // ── C07 — Archive Jobs ───────────────────────────────────────────────────────
  async createArchiveJob(payload: { archive_scope: string; record_ids: string[]; retention_policy_id?: string }): Promise<ArchiveJob> {
    const { data } = await api.post<ArchiveJob>("/data/archive/jobs", payload);
    return data;
  },

  async getArchiveJob(id: string): Promise<ArchiveJob> {
    const { data } = await api.get<ArchiveJob>(`/data/archive/jobs/${id}`);
    return data;
  },

  async restoreFromArchive(archive_id: string): Promise<RestoreJob> {
    const { data } = await api.post<RestoreJob>(`/data/archive/${archive_id}/restore`);
    return data;
  },

  // ── C07 — Crypto-Shred ───────────────────────────────────────────────────────
  async requestCryptoShred(payload: { subject_ref: string; affected_key_ids: string[]; affected_record_ids: string[] }): Promise<CryptoShredRequest> {
    const { data } = await api.post<CryptoShredRequest>("/privacy/crypto-shred", payload);
    return data;
  },

  async getCryptoShred(id: string): Promise<CryptoShredRequest> {
    const { data } = await api.get<CryptoShredRequest>(`/privacy/crypto-shred/${id}`);
    return data;
  },

  async verifyCryptoShred(id: string): Promise<CryptoShredVerification> {
    const { data } = await api.get<CryptoShredVerification>(`/privacy/crypto-shred/${id}/verify`);
    return data;
  },

  // ── C07 — Restore Jobs ───────────────────────────────────────────────────────
  async createRestoreJob(payload: { restore_type: string; restored_scope: string }): Promise<RestoreJob> {
    const { data } = await api.post<RestoreJob>("/data/restore/jobs", payload);
    return data;
  },

  async getRestoreJob(id: string): Promise<RestoreJob> {
    const { data } = await api.get<RestoreJob>(`/data/restore/jobs/${id}`);
    return data;
  },

  async getRestoreVerification(restore_job_id: string): Promise<RestoreVerification> {
    const { data } = await api.get<RestoreVerification>(`/data/restore/jobs/${restore_job_id}/verification`);
    return data;
  },

  async submitRestoreVerification(restore_job_id: string, checks: Record<string, boolean>): Promise<RestoreVerification> {
    const { data } = await api.post<RestoreVerification>(`/data/restore/jobs/${restore_job_id}/verify`, checks);
    return data;
  },

  async approveRestoreUse(restore_job_id: string): Promise<RestoreJob> {
    const { data } = await api.post<RestoreJob>(`/data/restore/jobs/${restore_job_id}/approve-use`);
    return data;
  },

  // ── C07 — Purge Jobs ─────────────────────────────────────────────────────────
  async createPurgeJob(payload: { purge_scope: string; record_count: number; retention_policy_id?: string; scope_ids?: string[] }): Promise<PurgeJob> {
    const { data } = await api.post<PurgeJob>("/data/purge/jobs", payload);
    return data;
  },

  async getPurgeJob(id: string): Promise<PurgeJob> {
    const { data } = await api.get<PurgeJob>(`/data/purge/jobs/${id}`);
    return data;
  },

  async approvePurge(id: string, approval_id: string): Promise<PurgeJob> {
    const { data } = await api.post<PurgeJob>(`/data/purge/jobs/${id}/approve`, { approval_id });
    return data;
  },

  // ── SC-003 — Shipment Exceptions (apiException = port 8020, apiException4 = port 8021) ──
  async listExceptionsPaged(filters?: { state?: string; page?: number; page_size?: number }): Promise<{
    exceptions: ShipmentException[]; total: number; page: number; pages: number;
  }> {
    if (USE_MOCK) { await delay(); return { exceptions: [], total: 0, page: 1, pages: 1 }; }
    const { data } = await apiException.get<{ exceptions: ShipmentException[]; total: number; page: number; pages: number }>(
      "/shipment-exceptions", { params: filters }
    );
    return data;
  },

  async getException(id: string): Promise<ShipmentException> {
    if (USE_MOCK) { await delay(); throw new Error("Not available in mock mode"); }
    const { data } = await apiException.get<ShipmentException>(`/shipment-exceptions/${id}`);
    return data;
  },

  async createException(payload: {
    carrier: string; shipment_reference: string;
    committed_eta: string; actual_delivery: string;
    penalty_rate_per_hour: number; penalty_cap: number; currency: string;
    origin?: string; destination?: string; description?: string;
    event_stream?: { event_type: string; occurred_at: string; location?: string; raw_payload?: Record<string, unknown> }[];
  }): Promise<ShipmentException> {
    if (USE_MOCK) { await delay(800); throw new Error("Not available in mock mode"); }
    const { data: job } = await apiException.post<{ job_id: string } | ShipmentException>(
      "/shipment-exceptions/submit", payload
    );
    if ("job_id" in job) {
      for (let i = 0; i < 45; i++) {
        await new Promise(r => setTimeout(r, 2000));
        const { data: s } = await apiException.get<{ status: string; case: ShipmentException | null; error: string | null }>(
          `/shipment-exceptions/submit-status/${job.job_id}`, { timeout: 8000 }
        );
        if (s.status === "done" && s.case) return s.case;
        if (s.status === "error") throw new Error(s.error || "Pipeline failed");
      }
      throw new Error("Timed out waiting for exception (90s)");
    }
    return job as ShipmentException;
  },

  async getExceptionFinding(caseId: string): Promise<{ id: string; confidence: number; rule_trace: unknown; created_at: string } | null> {
    if (USE_MOCK) { await delay(); return null; }
    try {
      const { data } = await apiException.get(`/shipment-exceptions/${caseId}/finding`);
      return data;
    } catch { return null; }
  },

  async getExceptionEvents(caseId: string): Promise<CaseEvent[]> {
    if (USE_MOCK) { await delay(); return []; }
    const { data } = await apiException.get<CaseEvent[]>(`/shipment-exceptions/${caseId}/events`);
    return data;
  },

  async getShipmentEvents(caseId: string): Promise<{ id: string; event_type: string; occurred_at: string; location?: string; carrier_id?: string; raw_payload?: unknown }[]> {
    if (USE_MOCK) { await delay(); return []; }
    try {
      const { data } = await apiException.get(`/shipment-exceptions/${caseId}/shipment-events`);
      return data;
    } catch { return []; }
  },

  async proposeExceptionCredit(caseId: string, payload: { finding_id: string; amount: number; currency: string }): Promise<unknown> {
    if (USE_MOCK) { await delay(500); throw new Error("Not available in mock mode"); }
    const { data } = await apiException.post(`/shipment-exceptions/${caseId}/propose`, payload);
    return data;
  },

  async decideExceptionCredit(caseId: string, payload: { task_id: string; decision: "APPROVE" | "REJECT"; note?: string }): Promise<unknown> {
    if (USE_MOCK) { await delay(500); throw new Error("Not available in mock mode"); }
    const { data } = await apiException.post(`/shipment-exceptions/${caseId}/decide`, payload);
    return data;
  },

  async executeException(payload: { case_id: string; token_id: string; action?: string }): Promise<{ status: string; envelope_id?: string; case_id: string; executed_at?: string }> {
    if (USE_MOCK) { await delay(1200); throw new Error("Not available in mock mode"); }
    const { data } = await apiException4.post("/execute", payload);
    return data;
  },

  async reconcileException(payload: { case_id: string; envelope_id: string }): Promise<unknown> {
    if (USE_MOCK) { await delay(800); throw new Error("Not available in mock mode"); }
    const { data } = await apiException4.post("/reconcile", payload);
    return data;
  },

  async getExceptionACR(caseId: string): Promise<{ acr_id: string; acr_root_hash: string; artifact_count: number; is_locked: boolean; issued_at: string } | null> {
    if (USE_MOCK) { await delay(); return null; }
    try {
      const { data } = await apiException4.get(`/cases/${caseId}/acr`);
      return data;
    } catch { return null; }
  },

  async issueExceptionACR(caseId: string, envelopeId: string): Promise<unknown> {
    if (USE_MOCK) { await delay(800); throw new Error("Not available in mock mode"); }
    const { data } = await apiException4.post(`/cases/${caseId}/acr`, { case_id: caseId, envelope_id: envelopeId });
    return data;
  },
};

// ── SC-004 Supplier Performance Scorecard ─────────────────────────────────────
export const scorecardApi = {
  async listCarriers(): Promise<string[]> {
    if (USE_MOCK) { await delay(200); return ["BlueDart", "FedEx", "DHL"]; }
    const { data } = await apiScore.get("/scorecards/carriers");
    return Array.isArray(data) ? data : [];
  },

  async listScorecards(carrierId?: string): Promise<ScorecardPeriod[]> {
    if (USE_MOCK) { await delay(300); return []; }
    const params: Record<string, string> = {};
    if (carrierId) params.carrier_id = carrierId;
    const { data } = await apiScore.get("/scorecards", { params });
    return Array.isArray(data) ? data : [];
  },

  async computeScorecard(carrierId: string, periodDays = 30, threshold = 70): Promise<ScorecardPeriod> {
    if (USE_MOCK) { await delay(800); throw new Error("Not available in mock mode"); }
    const { data } = await apiScore.post("/scorecards/compute", {
      carrier_id: carrierId,
      period_days: periodDays,
      contracted_threshold: threshold,
    });
    return data;
  },

  async getScorecard(id: string): Promise<ScorecardPeriod> {
    if (USE_MOCK) { await delay(300); throw new Error("Not available in mock mode"); }
    const { data } = await apiScore.get(`/scorecards/${id}`);
    return data;
  },

  async propose(scorecardId: string, findingId: string, amount: number, currency = "INR"): Promise<any> {
    if (USE_MOCK) { await delay(300); throw new Error("Not available in mock mode"); }
    const { data } = await apiScore.post(`/scorecards/${scorecardId}/propose`, {
      finding_id: findingId, amount, currency,
    });
    return data;
  },

  async decide(scorecardId: string, taskId: string, decision: "APPROVE" | "REJECT", note?: string): Promise<any> {
    if (USE_MOCK) { await delay(300); throw new Error("Not available in mock mode"); }
    const { data } = await apiScore.post(`/scorecards/${scorecardId}/decide`, {
      task_id: taskId, decision, note,
    });
    return data;
  },

  async execute(caseId: string, tokenId: string, actorSub: string): Promise<any> {
    if (USE_MOCK) { await delay(300); throw new Error("Not available in mock mode"); }
    const { data } = await apiScore4.post("/execute", {
      case_id: caseId, token_id: tokenId, actor_sub: actorSub, action: "NOTIFY_FLAG",
    });
    return data;
  },

  async reconcile(caseId: string, envelopeId: string, actorSub: string): Promise<any> {
    if (USE_MOCK) { await delay(300); throw new Error("Not available in mock mode"); }
    const { data } = await apiScore4.post("/reconcile", {
      case_id: caseId, envelope_id: envelopeId, actor_sub: actorSub,
    });
    return data;
  },

  async issueACR(caseId: string, actorSub: string): Promise<any> {
    if (USE_MOCK) { await delay(300); throw new Error("Not available in mock mode"); }
    const { data } = await apiScore4.post(`/cases/${caseId}/acr`, { actor_sub: actorSub });
    return data;
  },

  async getACR(caseId: string): Promise<any> {
    if (USE_MOCK) { await delay(300); return null; }
    const { data } = await apiScore4.get(`/cases/${caseId}/acr`);
    return data;
  },
};

// ── SC-005 Accessorial Dispute ────────────────────────────────────────────────
// apiAcc = port 8040 (gateway), apiAcc4 = port 8041 (execution)
export const accessorialApi = {
  async submit(data: unknown): Promise<any> {
    const { data: res } = await apiAcc.post("/accessorial-disputes/submit", data);
    return res;
  },

  async list(params?: Record<string, unknown>): Promise<any> {
    const { data: res } = await apiAcc.get("/accessorial-disputes", { params });
    return res;
  },

  async getById(id: string): Promise<any> {
    const { data: res } = await apiAcc.get("/accessorial-disputes/" + id);
    return res;
  },

  async getFinding(id: string): Promise<any> {
    const { data: res } = await apiAcc.get("/accessorial-disputes/" + id + "/finding");
    return res;
  },

  async getEvents(id: string): Promise<any> {
    const { data: res } = await apiAcc.get("/accessorial-disputes/" + id + "/events");
    return res;
  },

  async propose(id: string, data: unknown): Promise<any> {
    const { data: res } = await apiAcc.post("/accessorial-disputes/" + id + "/propose", data);
    return res;
  },

  async decide(id: string, data: unknown): Promise<any> {
    const { data: res } = await apiAcc.post("/accessorial-disputes/" + id + "/decide", data);
    return res;
  },

  async execute(caseId: string, tokenId: string, actorSub: string): Promise<any> {
    const { data: res } = await apiAcc4.post("/execute", {
      case_id: caseId, token_id: tokenId, actor_sub: actorSub, action: "ISSUE_PARTIAL_CREDIT",
    });
    return res;
  },

  async reconcile(caseId: string, envelopeId: string, actorSub: string): Promise<any> {
    const { data: res } = await apiAcc4.post("/reconcile", {
      case_id: caseId, envelope_id: envelopeId, actor_sub: actorSub,
    });
    return res;
  },

  async issueACR(caseId: string, actorSub: string): Promise<any> {
    const { data: res } = await apiAcc4.post("/cases/" + caseId + "/acr", { actor_sub: actorSub });
    return res;
  },

  async getACR(caseId: string): Promise<any> {
    const { data: res } = await apiAcc4.get("/cases/" + caseId + "/acr");
    return res;
  },
};

// ── Carrier types ─────────────────────────────────────────────────────────────
export interface CarrierItem {
  id:             string;
  name:           string;
  email:          string;
  address:        string;
  contact_person: string;
  contact_phone:  string;
  cc_emails:      string;
  created_at:     string;
}

// ── Tenant types ──────────────────────────────────────────────────────────────
export interface TenantItem {
  tenant_id:    string;
  display_name: string;
  slug:         string;
  status:       string;
  user_count:   number;
  created_at:   string;
}

export interface TenantCreateRequest {
  display_name:   string;
  slug:           string;
  admin_email:    string;
  admin_name:     string;
  admin_password: string;
}

export interface TenantCreateResponse {
  tenant_id:     string;
  display_name:  string;
  slug:          string;
  status:        string;
  admin_user_id: string;
  admin_email:   string;
  created_at:    string;
}
