import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { zoikoApi } from "@/api/zoiko";
import { formatCurrency } from "@/utils/cn";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar,
} from "recharts";
import {
  DollarSign, FileText, AlertTriangle, MessageSquare,
  TrendingUp, Zap, Target, BarChart2, FileDown,
} from "lucide-react";
import type { Case } from "@/types";

function KpiCard({ label, value, icon: Icon, iconBg, iconColor }: {
  label: string; value: string;
  icon: React.ElementType; iconBg: string; iconColor: string;
}) {
  return (
    <div className="bg-white rounded-xl border border-[#e8edf2] p-5 shadow-[0_1px_3px_rgba(0,0,0,0.06)]">
      <div className="flex items-start justify-between mb-3">
        <p className="text-[10px] font-bold uppercase tracking-widest text-[#94a3b8]">{label}</p>
        <div className="h-8 w-8 rounded-full flex items-center justify-center" style={{ background: iconBg }}>
          <Icon className="h-4 w-4" style={{ color: iconColor }} />
        </div>
      </div>
      <p className="text-[26px] font-extrabold text-[#1e293b] leading-none">{value}</p>
    </div>
  );
}

function RoiCard({ label, value, sub, iconColor, borderColor }: {
  label: string; value: string; sub?: string; iconColor: string; borderColor: string;
}) {
  return (
    <div className="bg-white rounded-xl border border-[#e8edf2] p-5 shadow-[0_1px_3px_rgba(0,0,0,0.06)]" style={{ borderTopColor: borderColor, borderTopWidth: 3 }}>
      <p className="text-[10px] font-bold uppercase tracking-widest mb-3" style={{ color: iconColor }}>{label}</p>
      <div className="h-5 w-8 rounded mb-2" style={{ background: iconColor }} />
      <p className="text-[22px] font-extrabold text-[#1e293b] leading-none">{value}</p>
      {sub && <p className="text-[11px] text-slate-400 mt-1.5 leading-tight">{sub}</p>}
    </div>
  );
}

function buildMonthlyData(cases: Case[]) {
  const map: Record<string, { overcharge: number; recovered: number }> = {};
  for (const c of cases) {
    const d    = new Date(c.opened_at);
    const key  = `${d.getFullYear()}-${String(d.getMonth()).padStart(2, "0")}`;
    if (!map[key]) map[key] = { overcharge: 0, recovered: 0 };
    map[key].overcharge += c.diff ?? 0;
    if (["DISPATCHED", "OUTCOME_RECORDED", "CLOSED"].includes(c.state))
      map[key].recovered += c.diff ?? 0;
  }
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const now    = new Date();
  return Array.from({ length: 6 }, (_, i) => {
    const d   = new Date(now.getFullYear(), now.getMonth() - (5 - i), 1);
    const key = `${d.getFullYear()}-${String(d.getMonth()).padStart(2, "0")}`;
    return {
      month:      months[d.getMonth()],
      overcharge: Math.round(map[key]?.overcharge ?? 0),
      recovered:  Math.round(map[key]?.recovered  ?? 0),
    };
  });
}

function buildCarrierData(cases: Case[]) {
  const map: Record<string, { total: number; overcharge: number; count: number }> = {};
  for (const c of cases) {
    const k = c.carrier || "Unknown";
    if (!map[k]) map[k] = { total: 0, overcharge: 0, count: 0 };
    map[k].total     += c.amount ?? 0;
    map[k].overcharge += c.diff ?? 0;
    map[k].count     += 1;
  }
  return Object.entries(map)
    .sort((a, b) => b[1].overcharge - a[1].overcharge)
    .slice(0, 6)
    .map(([carrier, v]) => ({ carrier, overcharge: Math.round(v.overcharge), count: v.count }));
}

export default function ReportsPage() {
  const { data: cases = [] } = useQuery({
    queryKey: ["cases"],
    queryFn:  () => zoikoApi.listCases(),
    refetchInterval: 30_000,
  });

  const { data: compliance } = useQuery({
    queryKey: ["reports-compliance"],
    queryFn:  async () => { const { data } = await api.get("/reports/compliance"); return data; },
    staleTime: 60_000,
  });

  const allCases = cases as Case[];

  const totalOvercharge = allCases.reduce((s, c) => s + (c.diff ?? 0), 0);
  const invoicesAudited = allCases.length;
  const errorsDetected  = allCases.filter(c => (c.diff ?? 0) > 0).length;
  const disputesFiled   = allCases.filter(c =>
    ["APPROVAL_PENDING","EXECUTION_READY","DISPATCHED","OUTCOME_RECORDED","CLOSED"].includes(c.state)
  ).length;
  const totalRecovered  = allCases
    .filter(c => ["DISPATCHED","OUTCOME_RECORDED","CLOSED"].includes(c.state))
    .reduce((s, c) => s + (c.diff ?? 0), 0);

  const subscriptionCost = 0;
  const pureProfitTotal  = totalRecovered - subscriptionCost;

  // monthly avg for projection
  const monthlyData = buildMonthlyData(allCases);
  const last3Avg    = monthlyData.slice(-3).reduce((s, m) => s + m.recovered, 0) / 3;
  const projAnnual  = Math.round(last3Avg * 12);

  const carrierData = buildCarrierData(allCases);

  return (
    <div className="space-y-6">

      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-[22px] font-extrabold text-[#1e293b]">Savings Dashboard</h1>
          <p className="text-[13px] text-slate-500 mt-0.5">
            Every rupee Zoiko found — by carrier, by month, and by dispute outcome.
          </p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2.5 bg-white border border-[#e2e8f0] text-[#374151] rounded-lg text-[12px] font-bold hover:bg-[#f8fafc] transition-colors shadow-sm">
          <FileDown className="h-4 w-4" />
          Monthly Summary PDF
        </button>
      </div>

      {/* ── KPI row ─────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard label="Total Overcharges Found" value={formatCurrency(totalOvercharge)} icon={DollarSign} iconBg="#dcfce7" iconColor="#16a34a" />
        <KpiCard label="Invoices Audited"         value={String(invoicesAudited)}          icon={FileText}   iconBg="#dbeafe" iconColor="#2563eb" />
        <KpiCard label="Billing Errors Detected"  value={String(errorsDetected)}           icon={TrendingUp} iconBg="#ffedd5" iconColor="#ea580c" />
        <KpiCard label="Disputes Filed"           value={String(disputesFiled)}            icon={MessageSquare} iconBg="#f3e8ff" iconColor="#7c3aed" />
      </div>

      {/* ── Pure Profit Banner ──────────────────────────────────────────── */}
      <div className="rounded-xl p-6 text-white" style={{ background: "linear-gradient(135deg, #15803d 0%, #16a34a 60%, #22c55e 100%)" }}>
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <p className="text-[11px] font-bold uppercase tracking-widest text-green-200 mb-2">Your Pure Profit</p>
            <p className="text-[42px] font-black leading-none">
              {pureProfitTotal >= 0 ? "+" : ""}{formatCurrency(pureProfitTotal)}
            </p>
            <p className="text-[13px] text-green-200 mt-2">
              Total Found ({formatCurrency(totalRecovered)}) — Subscription Cost ({formatCurrency(subscriptionCost)})
            </p>
          </div>
          <div className="text-right">
            <p className="text-[10px] font-bold uppercase tracking-widest text-green-300 mb-1">This Month</p>
            <p className="text-[28px] font-black leading-none">
              {monthlyData[5]?.recovered > 0 ? "+" : ""}{formatCurrency(monthlyData[5]?.recovered ?? 0)}
            </p>
            <p className="text-[11px] text-green-300 mt-1">
              {formatCurrency(monthlyData[5]?.overcharge ?? 0)} found — {formatCurrency(subscriptionCost)} fee
            </p>
          </div>
        </div>
      </div>

      {/* ── ROI Cards ───────────────────────────────────────────────────── */}
      <div>
        <p className="text-[10px] font-bold uppercase tracking-widest text-[#94a3b8] mb-3">Subscription ROI</p>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <RoiCard
            label="ROI Multiple"
            value={subscriptionCost > 0 ? `${(totalRecovered / subscriptionCost).toFixed(1)}×` : "∞"}
            sub={subscriptionCost > 0 ? "Returns vs subscription" : "Subscribe to track ROI"}
            iconColor="#22c55e"
            borderColor="#22c55e"
          />
          <RoiCard
            label="Payback Period"
            value={totalRecovered > 0 ? "< 1 mo" : "—"}
            sub={totalRecovered > 0 ? "Time to recover subscription cost" : "No recoveries yet"}
            iconColor="#64748b"
            borderColor="#64748b"
          />
          <RoiCard
            label="Projected Annual"
            value={projAnnual > 0 ? formatCurrency(projAnnual) : formatCurrency(0)}
            sub={`Based on trailing 3-month avg (${formatCurrency(Math.round(last3Avg))}/mo)`}
            iconColor="#ea580c"
            borderColor="#fed7aa"
          />
          <RoiCard
            label="Total Recovered"
            value={formatCurrency(totalRecovered)}
            sub="All time"
            iconColor="#7c3aed"
            borderColor="#e9d5ff"
          />
        </div>
      </div>

      {/* ── Charts row ──────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        {/* Monthly Trend */}
        <div className="bg-white rounded-xl border border-[#e8edf2] p-5 shadow-[0_1px_3px_rgba(0,0,0,0.06)]">
          <div className="flex items-center gap-2 mb-4">
            <BarChart2 className="h-4 w-4 text-slate-400" />
            <h3 className="text-[14px] font-bold text-[#1e293b]">Monthly Recovery vs Overcharge</h3>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={monthlyData} margin={{ top: 4, right: 4, left: -10, bottom: 0 }}>
              <defs>
                <linearGradient id="oGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#ef4444" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#ef4444" stopOpacity={0}   />
                </linearGradient>
                <linearGradient id="rGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#22c55e" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#22c55e" stopOpacity={0}   />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 4" stroke="#f1f5f9" vertical={false} />
              <XAxis dataKey="month" tick={{ fontSize: 11, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: "#94a3b8" }} axisLine={false} tickLine={false}
                tickFormatter={(v: number) => `₹${(v/1000).toFixed(0)}k`} />
              <Tooltip
                formatter={(v: number, n: string) => [formatCurrency(v), n === "overcharge" ? "Overcharged" : "Recovered"]}
                contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e2e8f0" }}
              />
              <Area type="monotone" dataKey="overcharge" stroke="#ef4444" strokeWidth={1.5} fill="url(#oGrad)" dot={false} />
              <Area type="monotone" dataKey="recovered"  stroke="#22c55e" strokeWidth={2}   fill="url(#rGrad)" dot={false} />
            </AreaChart>
          </ResponsiveContainer>
          <div className="flex gap-4 mt-2">
            {[{ color: "#ef4444", label: "Overcharged" }, { color: "#22c55e", label: "Recovered" }].map(l => (
              <div key={l.label} className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-sm" style={{ background: l.color }} />
                <span className="text-[11px] text-slate-500">{l.label}</span>
              </div>
            ))}
          </div>
        </div>

        {/* By Carrier */}
        <div className="bg-white rounded-xl border border-[#e8edf2] p-5 shadow-[0_1px_3px_rgba(0,0,0,0.06)]">
          <div className="flex items-center gap-2 mb-4">
            <Target className="h-4 w-4 text-slate-400" />
            <h3 className="text-[14px] font-bold text-[#1e293b]">Overcharges by Carrier</h3>
          </div>
          {carrierData.length === 0 ? (
            <div className="h-[200px] flex items-center justify-center text-center">
              <div>
                <BarChart2 className="h-8 w-8 text-slate-200 mx-auto mb-2" />
                <p className="text-[12px] text-slate-400">No overcharge data yet</p>
              </div>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={carrierData} layout="vertical" margin={{ top: 0, right: 8, left: 4, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 4" stroke="#f1f5f9" horizontal={false} />
                <XAxis type="number" tick={{ fontSize: 10, fill: "#94a3b8" }} axisLine={false} tickLine={false}
                  tickFormatter={(v: number) => `₹${(v/1000).toFixed(0)}k`} />
                <YAxis type="category" dataKey="carrier" tick={{ fontSize: 11, fill: "#374151" }} axisLine={false} tickLine={false} width={80} />
                <Tooltip
                  formatter={(v: number) => [formatCurrency(v), "Overcharge"]}
                  contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e2e8f0" }}
                />
                <Bar dataKey="overcharge" fill="#1d4ed8" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* ── Compliance summary ──────────────────────────────────────────── */}
      {compliance && (
        <div className="bg-white rounded-xl border border-[#e8edf2] p-5 shadow-[0_1px_3px_rgba(0,0,0,0.06)]">
          <div className="flex items-center gap-2 mb-4">
            <Zap className="h-4 w-4 text-slate-400" />
            <h3 className="text-[14px] font-bold text-[#1e293b]">Compliance Summary</h3>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { label: "Closure Rate",       value: `${Math.round((compliance.closure_rate ?? 0) * 100)}%` },
              { label: "Tokens Issued",      value: String(compliance.tokens_issued ?? 0)                  },
              { label: "ACR Records",        value: String(compliance.acr_count ?? 0)                      },
              { label: "WORM Entries",       value: String(compliance.worm_entries ?? 0)                   },
            ].map(item => (
              <div key={item.label} className="text-center">
                <p className="text-[22px] font-extrabold text-[#1e293b]">{item.value}</p>
                <p className="text-[10px] font-bold uppercase tracking-widest text-[#94a3b8] mt-1">{item.label}</p>
              </div>
            ))}
          </div>
        </div>
      )}

    </div>
  );
}
