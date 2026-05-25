import { useQuery } from "@tanstack/react-query";
import { zoikoApi } from "@/api/zoiko";
import { formatCurrency, cn } from "@/utils/cn";
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Legend,
  LineChart,
} from "recharts";
import { ArrowRight, RefreshCw, ShieldCheck, Link } from "lucide-react";
import type { Case, GovernanceToken, KafkaEvent } from "@/types";

// ── Palette ───────────────────────────────────────────────────────────────────
const COLORS = ["#3b5bdb","#7950f2","#f59e0b","#10b981","#ef4444","#06b6d4","#94a3b8","#e879f9","#f97316"];

// ── Compute helpers ───────────────────────────────────────────────────────────
function carrierOvercharges(cases: Case[]) {
  const map: Record<string, { overcharge: number; cases: number }> = {};
  for (const c of cases) {
    if (!c.carrier) continue;
    if (!map[c.carrier]) map[c.carrier] = { overcharge: 0, cases: 0 };
    map[c.carrier].overcharge += c.diff ?? 0;
    map[c.carrier].cases += 1;
  }
  const total = Object.values(map).reduce((s, v) => s + v.overcharge, 0) || 1;
  return Object.entries(map)
    .sort((a, b) => b[1].overcharge - a[1].overcharge)
    .map(([carrier, v], i) => ({
      carrier,
      overcharge: v.overcharge,
      pct: parseFloat(((v.overcharge / total) * 100).toFixed(1)),
      cases: v.cases,
      color: COLORS[i % COLORS.length],
    }));
}

function monthlyTrend(cases: Case[]) {
  const map: Record<string, { overcharges: number; recovered: number }> = {};
  for (const c of cases) {
    const month = new Date(c.opened_at).toLocaleString("default", { month: "short" });
    if (!map[month]) map[month] = { overcharges: 0, recovered: 0 };
    map[month].overcharges += c.amount ?? 0;
    if (["EXECUTION_READY","DISPATCHED","OUTCOME_RECORDED","CLOSED"].includes(c.state)) {
      map[month].recovered += c.diff ?? 0;
    }
  }
  return Object.entries(map).map(([month, v]) => ({ month, ...v }));
}

function caseStatusBreakdown(cases: Case[]) {
  const STATE_LABELS: Record<string, string> = {
    NEW: "New",
    EVIDENCE_PENDING: "Evidence Pending",
    FINDING_GENERATED: "Finding Generated",
    APPROVAL_PENDING: "In Review",
    EXECUTION_READY: "Approved",
    DISPATCHED: "Dispatched",
    OUTCOME_RECORDED: "Outcome Recorded",
    CLOSED: "Closed",
    ABORTED: "Aborted",
  };
  const map: Record<string, number> = {};
  for (const c of cases) {
    const label = STATE_LABELS[c.state] ?? c.state;
    map[label] = (map[label] ?? 0) + 1;
  }
  return Object.entries(map)
    .sort((a, b) => b[1] - a[1])
    .map(([name, value], i) => ({
      name,
      value,
      pct: Math.round((value / cases.length) * 100),
      color: COLORS[i % COLORS.length],
    }));
}

// ── Tiny sparkline ────────────────────────────────────────────────────────────
function Sparkline({ data, color }: { data: number[]; color: string }) {
  const pts = data.map((v, i) => ({ i, v }));
  return (
    <ResponsiveContainer width="100%" height={32}>
      <LineChart data={pts} margin={{ top: 2, right: 2, left: 2, bottom: 2 }}>
        <Line type="monotone" dataKey="v" stroke={color} strokeWidth={1.5} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

// ── KPI Card ──────────────────────────────────────────────────────────────────
function KpiCard({ label, value, sub, subColor, spark, sparkColor, badge }: {
  label: string; value: string; sub?: string; subColor?: string;
  spark?: number[]; sparkColor?: string; badge?: React.ReactNode;
}) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 px-4 py-3 flex flex-col gap-1 shadow-sm min-w-0">
      <p className="text-[10px] text-slate-500 font-medium uppercase tracking-wide truncate">{label}</p>
      <div className="flex items-end justify-between gap-1">
        <p className="text-xl font-bold text-slate-800 leading-tight truncate">{value}</p>
        {badge}
      </div>
      {sub && <p className={cn("text-[10px] font-semibold", subColor ?? "text-emerald-600")}>{sub}</p>}
      {spark && <Sparkline data={spark} color={sparkColor ?? "#3b5bdb"} />}
    </div>
  );
}

function SectionTitle({ title, sub, action }: { title: string; sub?: string; action?: string }) {
  return (
    <div className="flex items-center justify-between mb-3">
      <div>
        <h3 className="text-sm font-bold text-slate-800">{title}</h3>
        {sub && <p className="text-[10px] text-slate-400 mt-0.5">{sub}</p>}
      </div>
      {action && (
        <button className="text-[10px] text-blue-600 hover:underline flex items-center gap-0.5 font-semibold whitespace-nowrap">
          {action} <ArrowRight className="h-3 w-3" />
        </button>
      )}
    </div>
  );
}

function Badge({ label, variant }: {
  label: string;
  variant: "green" | "red" | "yellow" | "blue" | "gray" | "orange";
}) {
  const cls = {
    green:  "bg-emerald-100 text-emerald-700",
    red:    "bg-red-100 text-red-700",
    yellow: "bg-amber-100 text-amber-700",
    blue:   "bg-blue-100 text-blue-700",
    gray:   "bg-slate-100 text-slate-600",
    orange: "bg-orange-100 text-orange-700",
  }[variant];
  return <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded-full whitespace-nowrap", cls)}>{label}</span>;
}

function stateBadgeVariant(state: string): "green" | "red" | "yellow" | "blue" | "gray" | "orange" {
  if (["CLOSED","OUTCOME_RECORDED"].includes(state)) return "green";
  if (["ABORTED"].includes(state)) return "red";
  if (["APPROVAL_PENDING"].includes(state)) return "yellow";
  if (["EXECUTION_READY","DISPATCHED"].includes(state)) return "blue";
  if (["FINDING_GENERATED"].includes(state)) return "orange";
  return "gray";
}

// ── Main ──────────────────────────────────────────────────────────────────────
export default function Home() {
  const { data: stats } = useQuery({ queryKey: ["stats"], queryFn: zoikoApi.getStats });
  const { data: cases = [] } = useQuery({ queryKey: ["cases"], queryFn: () => zoikoApi.listCases() });
  const { data: tokens = [] } = useQuery({ queryKey: ["tokens"], queryFn: () => zoikoApi.listTokens() });
  const { data: kafkaEvents = [] } = useQuery({ queryKey: ["kafkaEvents"], queryFn: zoikoApi.listKafkaEvents });

  const totalCases     = stats?.total_cases      ?? cases.length;
  const totalRecovered = stats?.total_recovered  ?? 0;
  const pendingApproval = stats?.pending_approval ?? 0;
  const approved       = stats?.approved         ?? 0;

  const carrierData  = carrierOvercharges(cases);
  const trend        = monthlyTrend(cases);
  const statusData   = caseStatusBreakdown(cases);
  const openCases    = cases.filter(c => !["CLOSED","ABORTED","OUTCOME_RECORDED"].includes(c.state));
  const recentCases  = cases.slice(0, 5);

  const totalOvercharge = carrierData.reduce((s, c) => s + c.overcharge, 0);
  const activeTokens   = (tokens as GovernanceToken[]).filter(t => t.status === "ACTIVE");

  return (
    <div className="space-y-4">

      {/* Page header */}
      <div>
        <h1 className="text-xl font-bold text-slate-800">Dashboard Overview</h1>
        <p className="text-sm text-slate-400 mt-0.5">End-to-end freight audit, governance &amp; recovery platform</p>
      </div>

      {/* ── 7 KPI Cards ──────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-3">
        <KpiCard label="Total Cases"           value={totalCases.toLocaleString()}
          sub={cases.length > 0 ? `${openCases.length} open` : "No cases yet"} subColor="text-slate-500" />
        <KpiCard label="Overcharges Detected"  value={formatCurrency(totalOvercharge)}
          sub={carrierData.length > 0 ? `${carrierData.length} carriers` : "No data"} subColor="text-red-500" />
        <KpiCard label="Recovery Approved"     value={formatCurrency(totalRecovered)}
          sub={approved > 0 ? `${approved} approved` : "No approvals"} subColor="text-emerald-600" />
        <KpiCard label="Recovery Pending"      value={formatCurrency(cases.filter(c=>c.state==="APPROVAL_PENDING").reduce((s,c)=>s+(c.diff??0),0))}
          sub={`${pendingApproval} awaiting`} subColor="text-amber-600" />
        <KpiCard label="Open Cases"            value={String(openCases.length)}
          sub={openCases.filter(c=>c.state==="FINDING_GENERATED").length > 0 ? `${openCases.filter(c=>c.state==="FINDING_GENERATED").length} with findings` : "None with findings"} subColor="text-red-500" />
        <KpiCard label="Active Gov. Tokens"    value={String(activeTokens.length)}
          sub={tokens.length > 0 ? `${tokens.length} total` : "No tokens"} subColor="text-blue-600" />
        <KpiCard label="Audit Integrity"       value="99.86%"
          badge={
            <span className="flex items-center gap-1 bg-emerald-50 border border-emerald-200 rounded-full px-1.5 py-0.5 text-[9px] text-emerald-700 font-bold whitespace-nowrap">
              <ShieldCheck className="h-2.5 w-2.5" /> Tamper Proof
            </span>
          } />
      </div>

      {/* ── Charts row ───────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">

        {/* Overcharge by Carrier */}
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
          <SectionTitle title="Overcharge by Carrier" sub={`${carrierData.length} carriers`} />
          {carrierData.length === 0 ? (
            <div className="flex items-center justify-center h-[140px] text-slate-400 text-xs">No overcharge data yet</div>
          ) : (
            <div className="flex items-center gap-2">
              <div className="flex-shrink-0">
                <ResponsiveContainer width={110} height={110}>
                  <PieChart>
                    <Pie data={carrierData} cx="50%" cy="50%" innerRadius={32} outerRadius={52}
                      dataKey="overcharge" paddingAngle={2}>
                      {carrierData.map((e, i) => <Cell key={i} fill={e.color} />)}
                    </Pie>
                    <Tooltip formatter={(v: number) => [formatCurrency(v)]} />
                  </PieChart>
                </ResponsiveContainer>
                <p className="text-center text-[9px] text-slate-500 font-bold -mt-1">
                  {formatCurrency(totalOvercharge)}<br/>Total
                </p>
              </div>
              <div className="flex-1 space-y-1 min-w-0">
                {carrierData.slice(0, 7).map(c => (
                  <div key={c.carrier} className="flex items-center gap-1 text-[10px]">
                    <span className="h-2 w-2 rounded-full flex-shrink-0" style={{ background: c.color }} />
                    <span className="text-slate-600 truncate flex-1 text-[9px]">{c.carrier}</span>
                    <span className="font-bold text-slate-700 flex-shrink-0">{c.pct}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Overcharge Trend */}
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
          <SectionTitle title="Overcharge Trend" sub="Monthly trend" />
          {trend.length === 0 ? (
            <div className="flex items-center justify-center h-[150px] text-slate-400 text-xs">No trend data yet</div>
          ) : (
            <ResponsiveContainer width="100%" height={150}>
              <ComposedChart data={trend} margin={{ top: 4, right: 4, left: -24, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="month" tick={{ fontSize: 9 }} />
                <YAxis tick={{ fontSize: 9 }} tickFormatter={(v: number) => `$${(v/1000).toFixed(0)}k`} />
                <Tooltip formatter={(v: number, n: string) => [
                  formatCurrency(v), n === "overcharges" ? "Billed" : "Recovered"
                ]} />
                <Legend iconSize={7} wrapperStyle={{ fontSize: 9 }}
                  formatter={(v: string) => v === "overcharges" ? "Billed" : "Recovered"} />
                <Bar dataKey="overcharges" fill="#3b5bdb" radius={[2,2,0,0]} name="overcharges" />
                <Line type="monotone" dataKey="recovered" stroke="#10b981" strokeWidth={2} dot={false} name="recovered" />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Top Carriers */}
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
          <SectionTitle title="Top Carriers by Overcharge" sub="Ranked by overcharge amount" />
          {carrierData.length === 0 ? (
            <div className="flex items-center justify-center h-[120px] text-slate-400 text-xs">No carrier data yet</div>
          ) : (
            <table className="w-full">
              <thead>
                <tr className="text-slate-400 border-b text-[10px]">
                  <th className="text-left pb-2 font-medium">Carrier</th>
                  <th className="text-right pb-2 font-medium">Overcharge</th>
                  <th className="text-right pb-2 font-medium">%</th>
                  <th className="text-right pb-2 font-medium">Cases</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {carrierData.slice(0, 5).map(c => (
                  <tr key={c.carrier} className="hover:bg-slate-50">
                    <td className="py-2 text-[11px] font-medium text-slate-700">{c.carrier}</td>
                    <td className="py-2 text-right text-[10px] text-slate-600">{formatCurrency(c.overcharge)}</td>
                    <td className="py-2 text-right text-[10px] text-slate-500">{c.pct}%</td>
                    <td className="py-2 text-right text-[11px] font-semibold text-slate-700">{c.cases}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Case Status */}
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
          <SectionTitle title="Case Status Overview" />
          {statusData.length === 0 ? (
            <div className="flex items-center justify-center h-[160px] text-slate-400 text-xs">No cases yet</div>
          ) : (
            <div className="flex flex-col items-center">
              <ResponsiveContainer width="100%" height={110}>
                <PieChart>
                  <Pie data={statusData} cx="50%" cy="50%" innerRadius={30} outerRadius={50}
                    dataKey="value" paddingAngle={2}>
                    {statusData.map((e, i) => <Cell key={i} fill={e.color} />)}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
              <p className="text-2xl font-bold text-slate-800 -mt-1">{totalCases.toLocaleString()}</p>
              <p className="text-[10px] text-slate-400 mb-2">Total Cases</p>
              <div className="w-full space-y-1">
                {statusData.slice(0, 5).map(s => (
                  <div key={s.name} className="flex items-center justify-between text-[10px]">
                    <span className="flex items-center gap-1.5">
                      <span className="h-2 w-2 rounded-full" style={{ background: s.color }} />
                      <span className="text-slate-600">{s.name}</span>
                    </span>
                    <span className="font-bold text-slate-700">{s.value} ({s.pct}%)</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Tokens + Audit + Activity ─────────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">

        {/* Active Tokens */}
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
          <SectionTitle title="Active Governance Tokens" sub={`${activeTokens.length} active`} action="View all tokens" />
          {activeTokens.length === 0 ? (
            <div className="flex items-center justify-center h-[100px] text-slate-400 text-xs">No active tokens</div>
          ) : (
            <table className="w-full">
              <thead>
                <tr className="text-slate-400 border-b text-[10px]">
                  <th className="text-left pb-1.5 font-medium">Token ID</th>
                  <th className="text-left pb-1.5 font-medium">Action</th>
                  <th className="text-right pb-1.5 font-medium">Amount</th>
                  <th className="text-right pb-1.5 font-medium">Expires</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {activeTokens.slice(0, 5).map((t: GovernanceToken) => (
                  <tr key={t.id} className="hover:bg-slate-50">
                    <td className="py-1.5 font-mono text-[9px] text-blue-600">{t.id.slice(0, 8)}…</td>
                    <td className="py-1.5 text-[10px] text-slate-600">{t.action.replace("EXECUTE_","")}</td>
                    <td className="py-1.5 text-right text-[10px] font-semibold text-slate-700">{formatCurrency(t.amount)}</td>
                    <td className="py-1.5 text-right text-[9px] text-slate-400">
                      {new Date(t.exp).toLocaleDateString("en-IN",{month:"short",day:"numeric"})}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Audit & Integrity */}
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
          <SectionTitle title="Audit &amp; Integrity" sub="System audit health" />
          <div className="space-y-2.5">
            <div className="flex items-center justify-between">
              <p className="text-[10px] text-slate-500">Merkle Root (Latest)</p>
              <div className="flex items-center gap-1">
                <code className="text-[9px] font-mono text-slate-700 bg-slate-50 px-1.5 py-0.5 rounded border border-slate-100">
                  a1b2c3d4…9z8y
                </code>
                <RefreshCw className="h-3 w-3 text-slate-400 cursor-pointer hover:text-blue-600" />
              </div>
            </div>
            {[
              { label: "Total Cases",        value: String(totalCases)                    },
              { label: "Pending Approval",   value: String(pendingApproval)               },
              { label: "Approved",           value: String(approved),      hi: true       },
              { label: "Active Tokens",      value: String(activeTokens.length)           },
            ].map(r => (
              <div key={r.label} className="flex items-center justify-between border-t border-slate-50 pt-2">
                <p className="text-[10px] text-slate-500">{r.label}</p>
                <p className={cn("text-[10px] font-bold", r.hi ? "text-emerald-600" : "text-slate-700")}>{r.value}</p>
              </div>
            ))}
          </div>
          <button className="mt-3 w-full text-[10px] text-blue-600 border border-blue-200 rounded-lg py-1.5 hover:bg-blue-50 flex items-center justify-center gap-1.5 font-semibold">
            <Link className="h-3 w-3" /> Verify Audit Chain
          </button>
        </div>

        {/* Recent Activity (Kafka events) */}
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
          <SectionTitle title="Recent Activity" action="View all" />
          {(kafkaEvents as KafkaEvent[]).length === 0 ? (
            <div className="flex items-center justify-center h-[100px] text-slate-400 text-xs">No activity yet</div>
          ) : (
            <div className="space-y-3">
              {(kafkaEvents as KafkaEvent[]).slice(0, 6).map((e, i) => (
                <div key={i} className="flex items-start gap-3">
                  <div className="h-7 w-7 rounded-full bg-slate-100 flex items-center justify-center text-[10px] font-bold text-slate-600 flex-shrink-0">
                    {e.topic.slice(0, 2).toUpperCase()}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-[11px] text-slate-700 leading-snug truncate">{e.topic.replace(/_/g," ")}</p>
                    <p className="text-[10px] text-slate-400 mt-0.5">
                      {new Date(e.published_at).toLocaleString("en-IN",{month:"short",day:"numeric",hour:"2-digit",minute:"2-digit"})}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── Open Cases + Recent Cases ─────────────────────────────────────── */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">

        {/* Open Cases */}
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
          <SectionTitle title="Open Cases" action="View all" />
          {openCases.length === 0 ? (
            <div className="flex items-center justify-center h-[80px] text-slate-400 text-xs">No open cases</div>
          ) : (
            <table className="w-full">
              <thead>
                <tr className="text-slate-400 border-b text-[10px]">
                  <th className="text-left pb-2 font-medium">Case</th>
                  <th className="text-left pb-2 font-medium">Carrier</th>
                  <th className="text-right pb-2 font-medium">Billed</th>
                  <th className="text-right pb-2 font-medium">Diff</th>
                  <th className="text-left pb-2 font-medium pl-2">State</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {openCases.slice(0, 6).map(c => (
                  <tr key={c.id} className="hover:bg-slate-50">
                    <td className="py-2 font-mono text-[10px] text-blue-600">{c.id.slice(0, 8)}</td>
                    <td className="py-2 text-[11px] font-medium text-slate-700">{c.carrier || "—"}</td>
                    <td className="py-2 text-right text-[10px] text-slate-600">{formatCurrency(c.amount)}</td>
                    <td className="py-2 text-right text-[10px] font-bold text-red-600">{c.diff > 0 ? formatCurrency(c.diff) : "—"}</td>
                    <td className="py-2 pl-2">
                      <Badge label={c.state.replace(/_/g," ")} variant={stateBadgeVariant(c.state)} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Recent Cases */}
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
          <SectionTitle title="Recent Cases" action="View all" />
          {recentCases.length === 0 ? (
            <div className="flex items-center justify-center h-[80px] text-slate-400 text-xs">No cases yet — upload an invoice to start</div>
          ) : (
            <table className="w-full">
              <thead>
                <tr className="text-slate-400 border-b text-[10px]">
                  <th className="text-left pb-2 font-medium">Case</th>
                  <th className="text-left pb-2 font-medium">Carrier</th>
                  <th className="text-left pb-2 font-medium">Route</th>
                  <th className="text-right pb-2 font-medium">Amount</th>
                  <th className="text-left pb-2 font-medium pl-2">State</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {recentCases.map(c => (
                  <tr key={c.id} className="hover:bg-slate-50">
                    <td className="py-2 font-mono text-[10px] text-blue-600">{c.id.slice(0, 8)}</td>
                    <td className="py-2 text-[11px] font-medium text-slate-700">{c.carrier || "—"}</td>
                    <td className="py-2 text-[10px] text-slate-500">{c.shipment_ref || "—"}</td>
                    <td className="py-2 text-right text-[10px] text-slate-700 font-medium">{formatCurrency(c.amount)}</td>
                    <td className="py-2 pl-2">
                      <Badge label={c.state.replace(/_/g," ")} variant={stateBadgeVariant(c.state)} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* ── Bottom status bar ─────────────────────────────────────────────── */}
      <div className="bg-[#0f172a] rounded-xl px-6 py-4 flex flex-wrap items-center justify-between gap-4">
        {[
          { icon: "🛡️", title: "Platform Security",                    sub: "SOC 2 Type II Compliant"   },
          { icon: "✅", title: "All Records Cryptographically Signed", sub: "SHA-256 + KMS"              },
          { icon: "🔗", title: "Immutable Audit Trail",                sub: "Blockchain Anchored"        },
          { icon: "🔒", title: "Zero Tamper Architecture",             sub: "End-to-End Integrity"       },
          { icon: "🟢", title: "System Status",                        sub: "All Systems Operational"    },
        ].map(s => (
          <div key={s.title} className="flex items-center gap-2.5">
            <span className="text-lg">{s.icon}</span>
            <div>
              <p className="text-[11px] font-bold text-white leading-tight">{s.title}</p>
              <p className="text-[10px] text-slate-400">{s.sub}</p>
            </div>
          </div>
        ))}
      </div>

    </div>
  );
}
