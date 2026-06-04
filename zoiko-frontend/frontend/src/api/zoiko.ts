import { api, api3, api4, USE_MOCK } from "./client";
import * as mocks from "@/mocks/fixtures";
import type {
  Case, CanonicalInvoice, ValidationResult, EvidenceBundle, Finding,
  DecisionProposal, GovernanceToken, GovernanceDecision, CaseEvent,
  KafkaEvent, DashboardStats, SourceRecord, VarianceRecord, ACRBundle,
  ExecutionResult,
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

  // ---------- Dashboard ----------
  async getStats(): Promise<DashboardStats> {
    if (USE_MOCK) { await delay(); return mocks.mockStats; }
    const { data } = await api.get<DashboardStats>("/dashboard/stats");
    return data;
  },

  // ---------- Cases ----------
  async listCases(filters?: { state?: string }): Promise<Case[]> {
    if (USE_MOCK) {
      await delay();
      return filters?.state
        ? mocks.mockCases.filter(c => c.state === filters.state)
        : mocks.mockCases;
    }
    const { data } = await api.get<Case[]>("/cases", { params: filters });
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

  async createCase(payload: { invoice_number?: string; invoice_date?: string; transport_mode?: string; charge_lines?: {description:string;amount:number;type:string}[]; carrier: string; route: string; amount: number; currency: string }): Promise<Case> {
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
    const { data } = await api.get<VarianceRecord[]>(`/cases/${caseId}/variances`);
    return data;
  },

  async resolveVariance(caseId: string, varianceId: string, action: "RESOLVE" | "WAIVE"): Promise<VarianceRecord> {
    if (USE_MOCK) { await delay(300); return {} as VarianceRecord; }
    const { data } = await api.patch<VarianceRecord>(`/cases/${caseId}/variances/${varianceId}/resolve`, { action });
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
};

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
