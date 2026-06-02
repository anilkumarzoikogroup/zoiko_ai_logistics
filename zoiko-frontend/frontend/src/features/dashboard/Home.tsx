import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useAppSelector } from "@/store";
import { zoikoApi } from "@/api/zoiko";
import { formatCurrency, cn } from "@/utils/cn";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, LineChart, Line, Cell, PieChart, Pie,
} from "recharts";
import {
  TrendingUp, TrendingDown, CheckCircle2, Clock, Zap, FileText,
  AlertTriangle, ChevronRight, ShieldCheck, Award, ArrowRight,
  IndianRupee, BarChart3, Users, Truck,
} from "lucide-react";
import type { Case, GovernanceToken } from "@/types";

// ── Colour palette ────────────────────────────────────────────────────────────
const CARRIER_COLORS = ["#3b82f6","#8b5cf6","#f59e0b","#10b981","#ef4444","#06b6d4"];

// ── Customer-friendly state labels ────────────────────────────────────────────
const STATE_LABEL: Record<string, string> = {
  NEW:               "Submitted",
  EVIDENCE_PENDING:  "Collecting Evidence",
  FINDING_GENERATED: "AI Analyzed",
  APPROVAL_PENDING:  "Awaiting Approval",
  EXECUTION_READY:   "Approved",
  DISPATCHED:        "Recovery Initiated",
  OUTCOME_RECORDED:  "Recovered",
  CLOSED:            "Closed",
  ABORTED:           "Rejected",
};

const STATE_COLOR: Record<string, { bg: string; text: string }> = {
  NEW:               { bg: "#f1f5f9", text: "#64748b" },
  EVIDENCE_PENDING:  { bg: "#f1f5f9", text: "#64748b" },
  FINDING_GENERATED: { bg: "#ede9fe", text: "#7c3aed" },
  APPROVAL_PENDING:  { bg: "#fef3c7", text: "#d97706" },
  EXECUTION_READY:   { bg: "#dbeafe", text: "#2563eb" },
  DISPATCHED:        { bg: "#d1fae5", text: "#059669" },
  OUTCOME_RECORDED:  { bg: "#d1fae5", text: "#059669" },
  CLOSED:            { bg: "#d1fae5", text: "#059669" },
  ABORTED:           { bg: "#fee2e2", text: "#dc2626" },
};

// ── Helpers ───────────────────────────────────────────────────────────────────
function carrierBreakdown(cases: Case[]) {
  const map: Record<string, { overcharge: number; total: number; count: number }> = {};
  for (const c of cases) {
    if (!c.carrier) continue;
    if (!map[c.carrier]) map[c.carrier] = { overcharge: 0, total: 0, count: 0 };
    map[c.carrier].overcharge += c.diff ?? 0;
    map[c.carrier].total      += c.amount ?? 0;
    map[c.carrier].count      += 1;
  }
  return Object.entries(map)
    .sort((a, b) => b[1].overcharge - a[1].overcharge)
    .map(([carrier, v], i) => ({
      carrier,
      overcharge: Math.round(v.overcharge),
      total:      Math.round(v.total),
      count:      v.count,
      pct:        v.total > 0 ? parseFloat(((v.overcharge / v.total) * 100).toFixed(1)) : 0,
      color:      CARRIER_COLORS[i % CARRIER_COLORS.length],
    }));
}

function monthlyRecovery(cases: Case[]) {
  const map: Record<string, { billed: number; recovered: number }> = {};
  for (const c of cases) {
    const m = new Date(c.opened_at).toLocaleString("default", { month: "short" });
    if (!map[m]) map[m] = { billed: 0, recovered: 0 };
    map[m].billed    += c.diff ?? 0;
    if (["DISPATCHED","OUTCOME_RECORDED","CLOSED"].includes(c.state))
      map[m].recovered += c.diff ?? 0;
  }
  return Object.entries(map).slice(-6).map(([month, v]) => ({ month, ...v }));
}

// ── Sub-components ────────────────────────────────────────────────────────────
function StateBadge({ state }: { state: string }) {
  const cfg = STATE_COLOR[state] ?? { bg: "#f1f5f9", text: "#64748b" };
  return (
    <span style={{
      background: cfg.bg, color: cfg.text,
      fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 99, whiteSpace: "nowrap",
    }}>
      {STATE_LABEL[state] ?? state.replace(/_/g, " ")}
    </span>
  );
}

function KpiCard({
  label, value, sub, subUp, icon: Icon, accent, onClick,
}: {
  label: string; value: string; sub?: string; subUp?: boolean;
  icon: React.ElementType; accent: string; onClick?: () => void;
}) {
  return (
    <div
      onClick={onClick}
      style={{
        background: "#fff", border: "1px solid #e2e8f0", borderRadius: 12,
        padding: "16px 18px", boxShadow: "0 1px 4px rgba(0,0,0,0.04)",
        cursor: onClick ? "pointer" : "default", position: "relative", overflow: "hidden",
        transition: "box-shadow 0.15s, transform 0.15s",
      }}
      onMouseEnter={e => { if (onClick) { (e.currentTarget as HTMLDivElement).style.boxShadow = "0 4px 16px rgba(0,0,0,0.10)"; (e.currentTarget as HTMLDivElement).style.transform = "translateY(-1px)"; } }}
      onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.boxShadow = "0 1px 4px rgba(0,0,0,0.04)"; (e.currentTarget as HTMLDivElement).style.transform = "none"; }}
    >
      <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 3, borderRadius: "12px 12px 0 0", background: accent }} />
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <p style={{ fontSize: 11, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</p>
        <div style={{ width: 32, height: 32, borderRadius: 8, background: accent + "18", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Icon style={{ width: 15, height: 15, color: accent }} />
        </div>
      </div>
      <p style={{ fontSize: 22, fontWeight: 800, color: "#1e293b", margin: "0 0 4px" }}>{value}</p>
      {sub && (
        <div style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, color: subUp ? "#16a34a" : "#64748b", fontWeight: 600 }}>
          {subUp !== undefined && (
            subUp ? <TrendingUp style={{ width: 11, height: 11 }} /> : <TrendingDown style={{ width: 11, height: 11 }} />
          )}
          {sub}
        </div>
      )}
    </div>
  );
}

// ── Action Required Card ───────────────────────────────────────────────────────
function ActionCard({
  icon: Icon, title, count, amount, actionLabel, to, color,
}: {
  icon: React.ElementType; title: string; count: number;
  amount?: number; actionLabel: string; to: string; color: string;
}) {
  const nav = useNavigate();
  if (count === 0) return null;
  return (
    <div
      onClick={() => nav(to)}
      style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "12px 16px", background: color + "0d",
        border: `1px solid ${color}30`, borderRadius: 10, cursor: "pointer",
        transition: "background 0.15s",
      }}
      onMouseEnter={e => (e.currentTarget.style.background = color + "18")}
      onMouseLeave={e => (e.currentTarget.style.background = color + "0d")}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div style={{ width: 34, height: 34, borderRadius: 8, background: color + "20", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          <Icon style={{ width: 16, height: 16, color }} />
        </div>
        <div>
          <p style={{ fontSize: 13, fontWeight: 700, color: "#1e293b", margin: 0 }}>{title}</p>
          <p style={{ fontSize: 11, color: "#64748b", margin: 0 }}>
            {count} case{count !== 1 ? "s" : ""}
            {amount && amount > 0 ? ` · ${formatCurrency(amount)}` : ""}
          </p>
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span style={{ fontSize: 12, fontWeight: 700, color, background: color + "18", padding: "4px 10px", borderRadius: 6 }}>
          {actionLabel}
        </span>
        <ChevronRight style={{ width: 14, height: 14, color }} />
      </div>
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────
export default function Home() {
  const nav  = useNavigate();
  const user = useAppSelector(s => s.auth.user) || localStorage.getItem("zoiko_user") || "User";
  const role = useAppSelector(s => s.auth.role) || localStorage.getItem("zoiko_role") || "analyst";

  const { data: cases = [],  isLoading } = useQuery({ queryKey: ["cases"],  queryFn: () => zoikoApi.listCases() });
  const { data: tokens = [] }            = useQuery({ queryKey: ["tokens"], queryFn: () => zoikoApi.listTokens() });
  const { data: stats }                  = useQuery({ queryKey: ["stats"],  queryFn: zoikoApi.getStats });

  // ── Derived metrics ──────────────────────────────────────────────────────────
  const allCases        = cases as Case[];
  const allTokens       = tokens as GovernanceToken[];
  const carriers        = carrierBreakdown(allCases);
  const trend           = monthlyRecovery(allCases);

  const totalInvoices   = stats?.total_cases      ?? allCases.length;
  const totalOvercharge = allCases.reduce((s, c) => s + (c.diff ?? 0), 0);
  const totalRecovered  = allCases.filter(c => ["DISPATCHED","OUTCOME_RECORDED","CLOSED"].includes(c.state))
                                   .reduce((s, c) => s + (c.diff ?? 0), 0);
  const successRate     = totalOvercharge > 0
    ? Math.round((totalRecovered / totalOvercharge) * 100)
    : 0;

  // Role-based action items
  const needsProposal   = allCases.filter(c => c.state === "FINDING_GENERATED");
  const needsApproval   = allCases.filter(c => c.state === "APPROVAL_PENDING");
  const readyToExecute  = allCases.filter(c => c.state === "EXECUTION_READY");
  const activeTokens    = allTokens.filter(t => t.status === "ACTIVE");

  const pendingApprovalAmt = needsApproval.reduce((s, c) => s + (c.diff ?? 0), 0);
  const proposalAmt        = needsProposal.reduce((s, c) => s + (c.diff ?? 0), 0);
  const executeAmt         = readyToExecute.reduce((s, c) => s + (c.diff ?? 0), 0);

  const hasActions = needsProposal.length > 0 || needsApproval.length > 0
                  || readyToExecute.length > 0 || activeTokens.length > 0;

  const recentCases = allCases.slice(0, 8);
  const openCases   = allCases.filter(c => !["CLOSED","ABORTED"].includes(c.state));

  // Funnel data
  const funnelData = [
    { label: "Submitted",          value: allCases.length,                                                             color: "#3b82f6" },
    { label: "AI Analyzed",        value: allCases.filter(c => !["NEW","EVIDENCE_PENDING"].includes(c.state)).length, color: "#8b5cf6" },
    { label: "Awaiting Approval",  value: allCases.filter(c => c.state === "APPROVAL_PENDING").length,                color: "#f59e0b" },
    { label: "Recovered",          value: allCases.filter(c => ["DISPATCHED","OUTCOME_RECORDED","CLOSED"].includes(c.state)).length, color: "#10b981" },
  ];

  const firstName = user.split(" ")[0];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

      {/* ── Welcome banner ───────────────────────────────────────────────── */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 800, color: "#1e293b", margin: 0 }}>
            Welcome back, {firstName}
          </h1>
          <p style={{ fontSize: 13, color: "#64748b", margin: "2px 0 0" }}>
            {role === "analyst" && "Review flagged invoices and propose recoveries"}
            {role === "manager" && "Approve pending recovery proposals"}
            {role === "admin"   && "Freight overcharge recovery overview"}
          </p>
        </div>
        <button
          onClick={() => nav("/cases/new")}
          style={{
            display: "flex", alignItems: "center", gap: 7,
            padding: "9px 18px", background: "#2563eb", color: "#fff",
            border: "none", borderRadius: 8, fontSize: 13, fontWeight: 700,
            cursor: "pointer", boxShadow: "0 2px 8px rgba(37,99,235,0.3)",
          }}
        >
          <FileText style={{ width: 15, height: 15 }} />
          Submit Invoice
        </button>
      </div>

      {/* ── Action Required ───────────────────────────────────────────────── */}
      {hasActions && (
        <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 12, padding: "16px 18px", boxShadow: "0 1px 4px rgba(0,0,0,0.04)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 14 }}>
            <AlertTriangle style={{ width: 15, height: 15, color: "#f59e0b" }} />
            <p style={{ fontSize: 13, fontWeight: 700, color: "#1e293b", margin: 0 }}>Action Required</p>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {(role === "analyst" || role === "admin") && (
              <ActionCard icon={FileText}   title="Cases need your proposal"      count={needsProposal.length}  amount={proposalAmt}       actionLabel="Review Now"  to="/analyst"  color="#7c3aed" />
            )}
            {(role === "manager" || role === "admin") && (
              <ActionCard icon={CheckCircle2} title="Cases awaiting your approval" count={needsApproval.length}  amount={pendingApprovalAmt} actionLabel="Approve Now" to="/manager"  color="#d97706" />
            )}
            {(role === "manager" || role === "admin") && (
              <ActionCard icon={Zap}        title="Approved cases ready to execute" count={readyToExecute.length} amount={executeAmt}        actionLabel="Execute"     to="/execute" color="#2563eb" />
            )}
            {(role === "manager" || role === "admin") && activeTokens.length > 0 && (
              <ActionCard icon={Clock}      title="Active governance tokens expiring" count={activeTokens.length} amount={activeTokens.reduce((s,t)=>s+t.amount,0)} actionLabel="Execute Now" to="/execute" color="#dc2626" />
            )}
          </div>
        </div>
      )}

      {/* ── 4 KPI cards ───────────────────────────────────────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14 }}>
        <KpiCard
          label="Invoices Submitted"
          value={totalInvoices.toLocaleString("en-IN")}
          sub={`${openCases.length} in progress`}
          icon={FileText}
          accent="#3b82f6"
          onClick={() => nav("/cases")}
        />
        <KpiCard
          label="Overcharges Detected"
          value={formatCurrency(totalOvercharge)}
          sub={`${carriers.length} carrier${carriers.length !== 1 ? "s" : ""}`}
          subUp={false}
          icon={TrendingDown}
          accent="#ef4444"
        />
        <KpiCard
          label="Amount Recovered"
          value={formatCurrency(totalRecovered)}
          sub={`${allCases.filter(c=>["DISPATCHED","OUTCOME_RECORDED","CLOSED"].includes(c.state)).length} cases closed`}
          subUp
          icon={IndianRupee}
          accent="#10b981"
        />
        <KpiCard
          label="Recovery Rate"
          value={totalOvercharge > 0 ? `${successRate}%` : "—"}
          sub={totalOvercharge > 0 ? (successRate >= 70 ? "Above target" : "In progress") : "No data yet"}
          subUp={successRate >= 70}
          icon={Award}
          accent="#8b5cf6"
          onClick={() => nav("/analytics")}
        />
      </div>

      {/* ── Middle row: Carriers + Trend + Funnel ─────────────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1.2fr 0.9fr", gap: 14 }}>

        {/* Carrier Scorecard */}
        <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 12, padding: "16px 18px", boxShadow: "0 1px 4px rgba(0,0,0,0.04)" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
              <Truck style={{ width: 14, height: 14, color: "#64748b" }} />
              <p style={{ fontSize: 13, fontWeight: 700, color: "#1e293b", margin: 0 }}>Carrier Scorecard</p>
            </div>
            <button onClick={() => nav("/cases")} style={{ fontSize: 11, color: "#2563eb", fontWeight: 600, background: "none", border: "none", cursor: "pointer", display: "flex", alignItems: "center", gap: 2 }}>
              All <ChevronRight style={{ width: 12, height: 12 }} />
            </button>
          </div>
          {carriers.length === 0 ? (
            <div style={{ height: 140, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", color: "#cbd5e1", gap: 8 }}>
              <Truck style={{ width: 28, height: 28 }} />
              <p style={{ fontSize: 12, color: "#94a3b8", margin: 0 }}>No carrier data yet</p>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {carriers.slice(0, 5).map((c, i) => (
                <div key={c.carrier}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <span style={{ width: 8, height: 8, borderRadius: "50%", background: c.color, display: "inline-block", flexShrink: 0 }} />
                      <span style={{ fontSize: 12, fontWeight: 600, color: "#334155" }}>{c.carrier}</span>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <span style={{ fontSize: 11, fontWeight: 700, color: "#ef4444" }}>{formatCurrency(c.overcharge)}</span>
                      <span style={{ fontSize: 10, color: "#94a3b8", marginLeft: 5 }}>{c.pct}%</span>
                    </div>
                  </div>
                  <div style={{ background: "#f1f5f9", borderRadius: 99, height: 5, overflow: "hidden" }}>
                    <div style={{ height: "100%", borderRadius: 99, background: c.color, width: `${Math.min(c.pct, 100)}%`, transition: "width 0.8s ease" }} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Monthly Recovery Trend */}
        <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 12, padding: "16px 18px", boxShadow: "0 1px 4px rgba(0,0,0,0.04)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 14 }}>
            <BarChart3 style={{ width: 14, height: 14, color: "#64748b" }} />
            <p style={{ fontSize: 13, fontWeight: 700, color: "#1e293b", margin: 0 }}>Monthly Recovery</p>
          </div>
          {trend.length === 0 ? (
            <div style={{ height: 150, display: "flex", alignItems: "center", justifyContent: "center", color: "#94a3b8", fontSize: 12 }}>
              Submit invoices to see trend
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={trend} margin={{ top: 4, right: 4, left: -16, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                <XAxis dataKey="month" tick={{ fontSize: 10, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} axisLine={false} tickLine={false}
                       tickFormatter={(v: number) => `₹${(v/1000).toFixed(0)}k`} />
                <Tooltip
                  formatter={(v: number, n: string) => [formatCurrency(v), n === "billed" ? "Overcharged" : "Recovered"]}
                  contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid #e2e8f0" }}
                />
                <Bar dataKey="billed"    fill="#fee2e2" radius={[4,4,0,0]} name="billed"    />
                <Bar dataKey="recovered" fill="#10b981" radius={[4,4,0,0]} name="recovered" />
              </BarChart>
            </ResponsiveContainer>
          )}
          <div style={{ display: "flex", gap: 16, marginTop: 8 }}>
            {[{ color: "#fee2e2", border: "#fca5a5", label: "Overcharged" },
              { color: "#10b981", border: "#10b981", label: "Recovered"   }].map(l => (
              <div key={l.label} style={{ display: "flex", alignItems: "center", gap: 5 }}>
                <span style={{ width: 10, height: 10, borderRadius: 3, background: l.color, border: `1.5px solid ${l.border}`, display: "inline-block" }} />
                <span style={{ fontSize: 10, color: "#64748b" }}>{l.label}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Recovery Funnel */}
        <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 12, padding: "16px 18px", boxShadow: "0 1px 4px rgba(0,0,0,0.04)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 14 }}>
            <TrendingUp style={{ width: 14, height: 14, color: "#64748b" }} />
            <p style={{ fontSize: 13, fontWeight: 700, color: "#1e293b", margin: 0 }}>Recovery Pipeline</p>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {funnelData.map((f, i) => (
              <div key={f.label}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
                  <span style={{ fontSize: 11, color: "#475569", fontWeight: 600 }}>{f.label}</span>
                  <span style={{ fontSize: 12, fontWeight: 800, color: "#1e293b" }}>{f.value}</span>
                </div>
                <div style={{ background: "#f1f5f9", borderRadius: 99, height: 6, overflow: "hidden" }}>
                  <div style={{
                    height: "100%", borderRadius: 99, background: f.color,
                    width: `${funnelData[0].value > 0 ? Math.round((f.value / funnelData[0].value) * 100) : 0}%`,
                    transition: "width 0.8s ease",
                    opacity: 1 - i * 0.1,
                  }} />
                </div>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 14, paddingTop: 12, borderTop: "1px solid #f1f5f9" }}>
            <p style={{ fontSize: 10, color: "#94a3b8", margin: "0 0 2px", textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 700 }}>Pending Approval</p>
            <p style={{ fontSize: 16, fontWeight: 800, color: "#d97706", margin: 0 }}>
              {formatCurrency(pendingApprovalAmt)}
            </p>
            <p style={{ fontSize: 10, color: "#94a3b8", margin: "2px 0 0" }}>{needsApproval.length} cases waiting</p>
          </div>
        </div>
      </div>

      {/* ── Recent Cases ──────────────────────────────────────────────────── */}
      <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 12, overflow: "hidden", boxShadow: "0 1px 4px rgba(0,0,0,0.04)" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 18px", borderBottom: "1px solid #f1f5f9" }}>
          <p style={{ fontSize: 13, fontWeight: 700, color: "#1e293b", margin: 0 }}>Recent Cases</p>
          <button onClick={() => nav("/cases")} style={{ fontSize: 11, color: "#2563eb", fontWeight: 600, background: "none", border: "none", cursor: "pointer", display: "flex", alignItems: "center", gap: 2 }}>
            View all <ArrowRight style={{ width: 12, height: 12 }} />
          </button>
        </div>

        {isLoading ? (
          <div style={{ padding: 32, textAlign: "center", color: "#94a3b8", fontSize: 13 }}>Loading cases…</div>
        ) : recentCases.length === 0 ? (
          <div style={{ padding: 48, textAlign: "center" }}>
            <FileText style={{ width: 32, height: 32, color: "#cbd5e1", margin: "0 auto 10px" }} />
            <p style={{ fontSize: 14, color: "#64748b", margin: 0 }}>No cases yet</p>
            <p style={{ fontSize: 12, color: "#94a3b8", marginTop: 4 }}>Submit your first invoice to start detecting overcharges</p>
            <button
              onClick={() => nav("/cases/new")}
              style={{ marginTop: 14, padding: "8px 18px", background: "#2563eb", color: "#fff", border: "none", borderRadius: 7, fontSize: 12, fontWeight: 700, cursor: "pointer" }}
            >
              Submit Invoice
            </button>
          </div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: "#f8fafc" }}>
                {["Case ID", "Carrier", "Invoice Amount", "Overcharge", "AI Confidence", "Status", "Date"].map(h => (
                  <th key={h} style={{ padding: "9px 16px", textAlign: "left", fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.05em", borderBottom: "1px solid #f1f5f9" }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {recentCases.map((c: Case, i: number) => (
                <tr
                  key={c.id}
                  onClick={() => nav(`/cases/${c.id}`)}
                  style={{ cursor: "pointer", borderBottom: i < recentCases.length - 1 ? "1px solid #f8fafc" : "none", transition: "background 0.1s" }}
                  onMouseEnter={e => (e.currentTarget.style.background = "#f8fafc")}
                  onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
                >
                  <td style={{ padding: "11px 16px", fontFamily: "monospace", fontSize: 11, color: "#2563eb" }}>{c.id.slice(0, 8)}…</td>
                  <td style={{ padding: "11px 16px", fontSize: 12, fontWeight: 600, color: "#334155" }}>{c.carrier || "—"}</td>
                  <td style={{ padding: "11px 16px", fontSize: 12, color: "#334155" }}>{formatCurrency(c.amount)}</td>
                  <td style={{ padding: "11px 16px", fontSize: 12, fontWeight: 700, color: c.diff > 0 ? "#dc2626" : "#94a3b8" }}>
                    {c.diff > 0 ? formatCurrency(c.diff) : "—"}
                  </td>
                  <td style={{ padding: "11px 16px" }}>
                    {c.confidence ? (
                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <div style={{ width: 40, height: 5, background: "#f1f5f9", borderRadius: 99, overflow: "hidden" }}>
                          <div style={{ height: "100%", background: c.confidence >= 0.9 ? "#10b981" : c.confidence >= 0.7 ? "#f59e0b" : "#ef4444", width: `${c.confidence * 100}%`, borderRadius: 99 }} />
                        </div>
                        <span style={{ fontSize: 11, fontWeight: 700, color: "#475569" }}>{(c.confidence * 100).toFixed(0)}%</span>
                      </div>
                    ) : <span style={{ fontSize: 11, color: "#cbd5e1" }}>—</span>}
                  </td>
                  <td style={{ padding: "11px 16px" }}><StateBadge state={c.state} /></td>
                  <td style={{ padding: "11px 16px", fontSize: 11, color: "#94a3b8" }}>
                    {new Date(c.opened_at).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* ── Trust footer ──────────────────────────────────────────────────── */}
      <div style={{
        background: "linear-gradient(135deg, #0f172a 0%, #1e293b 100%)",
        borderRadius: 12, padding: "16px 24px",
        display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 16,
      }}>
        {[
          { icon: ShieldCheck, title: "Cryptographically Signed",    sub: "Ed25519 + SHA-256 on every record"  },
          { icon: CheckCircle2, title: "Two-Person Approval",        sub: "Analyst proposes · Manager approves" },
          { icon: Award,        title: "Immutable Audit Trail",      sub: "WORM-locked, tamper-proof"           },
          { icon: Users,        title: "Role-Based Access",          sub: "Analyst · Manager · Admin"           },
        ].map(s => (
          <div key={s.title} style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 32, height: 32, borderRadius: 8, background: "rgba(255,255,255,0.07)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
              <s.icon style={{ width: 15, height: 15, color: "#60a5fa" }} />
            </div>
            <div>
              <p style={{ fontSize: 11, fontWeight: 700, color: "#fff", margin: 0 }}>{s.title}</p>
              <p style={{ fontSize: 10, color: "#64748b", margin: 0 }}>{s.sub}</p>
            </div>
          </div>
        ))}
      </div>

    </div>
  );
}
