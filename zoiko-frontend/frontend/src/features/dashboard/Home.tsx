import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { zoikoApi } from "@/api/zoiko";
import { formatCurrency } from "@/utils/cn";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import {
  DollarSign, FileText, AlertTriangle, MessageSquare,
  Upload, ArrowRight, ChevronRight, Gift,
  BarChart2, FileCheck, LayoutDashboard,
} from "lucide-react";
import type { Case } from "@/types";

// ── Helpers ───────────────────────────────────────────────────────────────────
function monthlyRecovery(cases: Case[]) {
  const map: Record<string, number> = {};
  const order: string[] = [];
  for (const c of cases) {
    const d = new Date(c.opened_at);
    const key = d.toLocaleString("default", { month: "short", year: "2-digit" });
    const label = d.toLocaleString("default", { month: "short" });
    if (!map[key]) { map[key] = 0; order.push(key); }
    if (["DISPATCHED", "OUTCOME_RECORDED", "CLOSED"].includes(c.state))
      map[key] += c.diff ?? 0;
    return { month: label, amount: Math.round(map[key]) };
  }
  // ensure at least 6 months including current
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const now = new Date();
  const result: { month: string; amount: number }[] = [];
  for (let i = 5; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const label = months[d.getMonth()];
    const key = `${label} ${String(d.getFullYear()).slice(2)}`;
    result.push({ month: label, amount: Math.round(map[key] ?? 0) });
  }
  return result;
}

function buildMonthlyData(cases: Case[]) {
  const map: Record<string, number> = {};
  for (const c of cases) {
    const d = new Date(c.opened_at);
    const key = `${d.getFullYear()}-${String(d.getMonth()).padStart(2, "0")}`;
    if (!map[key]) map[key] = 0;
    if (["DISPATCHED", "OUTCOME_RECORDED", "CLOSED"].includes(c.state))
      map[key] += c.diff ?? 0;
  }
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const now = new Date();
  return Array.from({ length: 6 }, (_, i) => {
    const d = new Date(now.getFullYear(), now.getMonth() - (5 - i), 1);
    const key = `${d.getFullYear()}-${String(d.getMonth()).padStart(2, "0")}`;
    return { month: months[d.getMonth()], amount: Math.round(map[key] ?? 0) };
  });
}

// ── KPI Card — matches FreightDetective style ─────────────────────────────────
function KpiCard({ label, value, icon: Icon, iconBg, iconColor }: {
  label: string; value: string;
  icon: React.ElementType; iconBg: string; iconColor: string;
}) {
  return (
    <div className="bg-white rounded-xl border border-[#e8edf2] p-5 shadow-[0_1px_3px_rgba(0,0,0,0.06)]">
      <div className="flex items-start justify-between mb-3">
        <p className="text-[10px] font-bold uppercase tracking-widest text-[#94a3b8]">{label}</p>
        <div className="h-8 w-8 rounded-full flex items-center justify-center flex-shrink-0" style={{ background: iconBg }}>
          <Icon className="h-4 w-4" style={{ color: iconColor }} />
        </div>
      </div>
      <p className="text-[26px] font-extrabold text-[#1e293b] leading-none">{value}</p>
    </div>
  );
}

// ── Quick Action Row ──────────────────────────────────────────────────────────
function QuickAction({ icon: Icon, label, primary, onClick }: {
  icon: React.ElementType; label: string; primary?: boolean; onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={[
        "w-full flex items-center gap-3 px-4 py-3 rounded-lg text-[13px] font-semibold transition-all",
        primary
          ? "bg-[#0d2137] hover:bg-[#1a3a5c] text-white"
          : "bg-[#f4f6f9] hover:bg-[#eaecf0] text-[#374151]",
      ].join(" ")}
    >
      <Icon className="h-4 w-4 flex-shrink-0" />
      <span className="flex-1 text-left">{label}</span>
      <ArrowRight className="h-4 w-4 flex-shrink-0 opacity-60" />
    </button>
  );
}

// ── Status badge ──────────────────────────────────────────────────────────────
const STATUS_MAP: Record<string, { label: string; cls: string }> = {
  CLOSED:            { label: "completed",       cls: "bg-[#dcfce7] text-[#16a34a]"  },
  DISPATCHED:        { label: "completed",       cls: "bg-[#dcfce7] text-[#16a34a]"  },
  OUTCOME_RECORDED:  { label: "completed",       cls: "bg-[#dcfce7] text-[#16a34a]"  },
  FINDING_GENERATED: { label: "ai analyzed",     cls: "bg-[#f3e8ff] text-[#7c3aed]"  },
  APPROVAL_PENDING:  { label: "pending approval",cls: "bg-[#fef3c7] text-[#d97706]"  },
  EXECUTION_READY:   { label: "ready",           cls: "bg-[#dbeafe] text-[#2563eb]"  },
  NEW:               { label: "processing",      cls: "bg-[#f1f5f9] text-[#64748b]"  },
  EVIDENCE_PENDING:  { label: "processing",      cls: "bg-[#f1f5f9] text-[#64748b]"  },
  ABORTED:           { label: "rejected",        cls: "bg-[#fee2e2] text-[#dc2626]"  },
};

function StatusBadge({ state }: { state: string }) {
  const s = STATUS_MAP[state] ?? { label: state.toLowerCase(), cls: "bg-[#f1f5f9] text-[#64748b]" };
  return (
    <span className={`inline-block text-[10px] font-bold px-2.5 py-1 rounded-full ${s.cls}`}>
      {s.label}
    </span>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────
export default function Home() {
  const nav = useNavigate();

  const { data: cases = [], isLoading } = useQuery({
    queryKey: ["cases"],
    queryFn:  () => zoikoApi.listCases(),
    refetchInterval: 8000,
  });

  const allCases = cases as Case[];

  // KPI calculations
  const totalOvercharge = allCases.reduce((s, c) => s + (c.diff ?? 0), 0);
  const invoicesAudited = allCases.length;
  const errorsDetected  = allCases.filter(c => (c.diff ?? 0) > 0).length;
  const disputesFiled   = allCases.filter(c =>
    ["APPROVAL_PENDING", "EXECUTION_READY", "DISPATCHED", "OUTCOME_RECORDED", "CLOSED"].includes(c.state)
  ).length;

  const chartData = buildMonthlyData(allCases);

  const recentInvoices = [...allCases]
    .sort((a, b) => new Date(b.opened_at).getTime() - new Date(a.opened_at).getTime())
    .slice(0, 5);

  const recentDisputes = allCases
    .filter(c => ["APPROVAL_PENDING", "ABORTED"].includes(c.state))
    .slice(0, 5);

  const fmtDate = (iso: string) =>
    new Date(iso).toLocaleDateString("en-IN", { month: "short", day: "numeric", year: "numeric" });

  return (
    <div className="space-y-5">

      {/* ── KPI row ─────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          label="Total Overcharges Found"
          value={isLoading ? "—" : formatCurrency(totalOvercharge)}
          icon={DollarSign}
          iconBg="#dcfce7"
          iconColor="#16a34a"
        />
        <KpiCard
          label="Invoices Audited"
          value={isLoading ? "—" : String(invoicesAudited)}
          icon={FileText}
          iconBg="#dbeafe"
          iconColor="#2563eb"
        />
        <KpiCard
          label="Errors Detected"
          value={isLoading ? "—" : String(errorsDetected)}
          icon={AlertTriangle}
          iconBg="#ffedd5"
          iconColor="#ea580c"
        />
        <KpiCard
          label="Disputes Filed"
          value={isLoading ? "—" : String(disputesFiled)}
          icon={MessageSquare}
          iconBg="#f3e8ff"
          iconColor="#7c3aed"
        />
      </div>

      {/* ── Chart + Quick Actions ───────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-4">

        {/* Funds Recovered Over Time */}
        <div className="bg-white rounded-xl border border-[#e8edf2] p-5 shadow-[0_1px_3px_rgba(0,0,0,0.06)]">
          <div className="flex items-center gap-2 mb-5">
            <BarChart2 className="h-4 w-4 text-slate-500" />
            <h2 className="text-[14px] font-bold text-[#1e293b]">Funds Recovered Over Time</h2>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={chartData} margin={{ top: 4, right: 4, left: -10, bottom: 0 }}>
              <defs>
                <linearGradient id="recGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#1d4ed8" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="#1d4ed8" stopOpacity={0}    />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 4" stroke="#f1f5f9" vertical={false} />
              <XAxis
                dataKey="month"
                tick={{ fontSize: 11, fill: "#94a3b8" }}
                axisLine={false} tickLine={false}
              />
              <YAxis
                tick={{ fontSize: 11, fill: "#94a3b8" }}
                axisLine={false} tickLine={false}
                tickFormatter={(v: number) => `₹${(v / 1000).toFixed(0)}k`}
              />
              <Tooltip
                formatter={(v: number) => [formatCurrency(v), "Recovered"]}
                contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e2e8f0", boxShadow: "0 2px 8px rgba(0,0,0,0.08)" }}
                cursor={{ stroke: "#e2e8f0" }}
              />
              <Area
                type="monotone"
                dataKey="amount"
                stroke="#1d4ed8"
                strokeWidth={2}
                fill="url(#recGradient)"
                dot={false}
                activeDot={{ r: 4, strokeWidth: 0, fill: "#1d4ed8" }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Quick Actions */}
        <div className="bg-white rounded-xl border border-[#e8edf2] p-5 shadow-[0_1px_3px_rgba(0,0,0,0.06)]">
          <h2 className="text-[14px] font-bold text-[#1e293b] mb-4">Quick Actions</h2>
          <div className="space-y-2">
            <QuickAction icon={Upload}        label="Upload New Invoice"  primary onClick={() => nav("/cases/new")}     />
            <QuickAction icon={FileText}      label="View All Invoices"           onClick={() => nav("/cases")}         />
            <QuickAction icon={MessageSquare} label="Open Disputes"               onClick={() => nav("/disputes")}      />
            <QuickAction icon={FileCheck}     label="Manage Contracts"            onClick={() => nav("/rate-control")}  />
            <QuickAction icon={BarChart2}     label="Analytics Report"            onClick={() => nav("/analytics")}     />
          </div>
        </div>
      </div>

      {/* ── Recent Invoices + Recent Disputes ──────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        {/* Recent Invoices */}
        <div className="bg-white rounded-xl border border-[#e8edf2] shadow-[0_1px_3px_rgba(0,0,0,0.06)] overflow-hidden">
          <div className="flex items-center justify-between px-5 py-4 border-b border-[#f1f5f9]">
            <h2 className="text-[14px] font-bold text-[#1e293b]">Recent Invoices</h2>
            <button
              onClick={() => nav("/cases")}
              className="flex items-center gap-1 text-[12px] font-semibold text-[#374151] hover:text-[#1e293b] transition-colors"
            >
              View All <ArrowRight className="h-3.5 w-3.5" />
            </button>
          </div>

          {isLoading ? (
            <div className="divide-y divide-[#f8fafc]">
              {[1,2,3].map(i => (
                <div key={i} className="px-5 py-3.5 flex items-center gap-3 animate-pulse">
                  <div className="flex-1 space-y-1.5">
                    <div className="h-3 w-36 bg-slate-100 rounded" />
                    <div className="h-2.5 w-24 bg-slate-100 rounded" />
                  </div>
                  <div className="h-3 w-16 bg-slate-100 rounded" />
                  <div className="h-5 w-20 bg-slate-100 rounded-full" />
                </div>
              ))}
            </div>
          ) : recentInvoices.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 gap-3">
              <div className="h-12 w-12 rounded-xl bg-[#f8fafc] border border-[#e8edf2] flex items-center justify-center">
                <FileText className="h-5 w-5 text-slate-300" />
              </div>
              <div className="text-center">
                <p className="text-[13px] font-semibold text-[#374151]">No invoices yet</p>
                <p className="text-[11px] text-slate-400 mt-0.5">Upload your first invoice to start</p>
              </div>
              <button
                onClick={() => nav("/cases/new")}
                className="mt-1 flex items-center gap-1.5 px-4 py-2 bg-[#0d2137] hover:bg-[#1a3a5c] text-white rounded-lg text-[12px] font-bold transition-colors"
              >
                <Upload className="h-3.5 w-3.5" /> Upload Invoice
              </button>
            </div>
          ) : (
            <div className="divide-y divide-[#f8fafc]">
              {recentInvoices.map((c: Case) => (
                <div
                  key={c.id}
                  onClick={() => nav(`/cases/${c.id}`)}
                  className="flex items-center gap-3 px-5 py-3.5 hover:bg-[#f8fafc] cursor-pointer transition-colors"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-[13px] font-bold text-[#1e293b] truncate">{c.carrier || "Unknown Carrier"}</p>
                    <p className="text-[11px] text-slate-400 mt-0.5">
                      {c.id.slice(0, 8).toUpperCase()} · {fmtDate(c.opened_at)}
                    </p>
                  </div>
                  <span className="text-[13px] font-bold text-[#1e293b] flex-shrink-0">
                    {formatCurrency(c.amount, c.currency)}
                  </span>
                  <StatusBadge state={c.state} />
                  <ChevronRight className="h-4 w-4 text-slate-300 flex-shrink-0" />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Recent Disputes */}
        <div className="bg-white rounded-xl border border-[#e8edf2] shadow-[0_1px_3px_rgba(0,0,0,0.06)] overflow-hidden">
          <div className="flex items-center justify-between px-5 py-4 border-b border-[#f1f5f9]">
            <h2 className="text-[14px] font-bold text-[#1e293b]">Recent Disputes</h2>
            <button
              onClick={() => nav("/disputes")}
              className="flex items-center gap-1 text-[12px] font-semibold text-[#374151] hover:text-[#1e293b] transition-colors"
            >
              View All <ArrowRight className="h-3.5 w-3.5" />
            </button>
          </div>

          {recentDisputes.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 gap-2">
              <MessageSquare className="h-10 w-10 text-slate-200" />
              <p className="text-[13px] font-semibold text-[#374151]">No disputes yet</p>
              <p className="text-[11px] text-slate-400">Disputes are auto-generated when errors are found</p>
            </div>
          ) : (
            <div className="divide-y divide-[#f8fafc]">
              {recentDisputes.map((c: Case) => (
                <div
                  key={c.id}
                  onClick={() => nav(`/cases/${c.id}`)}
                  className="flex items-center gap-3 px-5 py-3.5 hover:bg-[#f8fafc] cursor-pointer transition-colors"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-[13px] font-bold text-[#1e293b] truncate">{c.carrier || "Unknown Carrier"}</p>
                    <p className="text-[11px] text-slate-400 mt-0.5">
                      {c.id.slice(0, 8).toUpperCase()} · {fmtDate(c.opened_at)}
                    </p>
                  </div>
                  <span className="text-[13px] font-bold text-red-600 flex-shrink-0">
                    {(c.diff ?? 0) > 0 ? formatCurrency(c.diff, c.currency) : "—"}
                  </span>
                  <StatusBadge state={c.state} />
                  <ChevronRight className="h-4 w-4 text-slate-300 flex-shrink-0" />
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── Referral banner ─────────────────────────────────────────────── */}
      <div className="bg-[#fffbeb] border border-[#fde68a] rounded-xl px-5 py-4 flex items-center gap-4">
        <div className="h-10 w-10 rounded-full bg-[#fef3c7] flex items-center justify-center flex-shrink-0">
          <Gift className="h-5 w-5 text-[#d97706]" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-[13px] font-bold text-[#92400e]">Invite your team — collaborate on overcharge recovery</p>
          <p className="text-[12px] text-[#b45309] mt-0.5">Add analysts and managers to review and approve cases together.</p>
        </div>
        <button
          onClick={() => nav("/users")}
          className="flex items-center gap-1.5 px-4 py-2 border border-[#f59e0b] text-[#d97706] rounded-lg text-[12px] font-bold hover:bg-[#fef3c7] transition-colors flex-shrink-0 whitespace-nowrap"
        >
          <LayoutDashboard className="h-3.5 w-3.5" />
          Invite Team
        </button>
      </div>

    </div>
  );
}
