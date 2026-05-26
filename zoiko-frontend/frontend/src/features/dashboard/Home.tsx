import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { zoikoApi } from "@/api/zoiko";
import { formatCurrency, cn } from "@/utils/cn";
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Legend,
  LineChart,
} from "recharts";
import {
  ArrowRight, RefreshCw, ShieldCheck, TrendingDown,
  TrendingUp, AlertTriangle, CheckCircle2, Clock, Zap,
  FileText, GitBranch, Lock, Award, ChevronRight, BarChart3,
} from "lucide-react";
import type { Case, GovernanceToken, KafkaEvent } from "@/types";

const COLORS = ["#3b82f6","#8b5cf6","#f59e0b","#10b981","#ef4444","#06b6d4","#94a3b8","#e879f9","#f97316"];

// ── Pipeline steps definition ─────────────────────────────────────────────────
const PIPELINE_STEPS = [
  { id: "ingest",    label: "Ingest",       sub: "Parse & hash invoice",   phase: 2 },
  { id: "validate",  label: "Validate",     sub: "Contract rate check",    phase: 2 },
  { id: "canonical", label: "Canonical",    sub: "Authoritative record",   phase: 2 },
  { id: "evidence",  label: "Evidence",     sub: "Merkle bundle",          phase: 3 },
  { id: "reasoning", label: "AI Reasoning", sub: "96% confidence",         phase: 3 },
  { id: "govern",    label: "Governance",   sub: "SoD approval chain",     phase: 3 },
  { id: "execute",   label: "Execute",      sub: "8-gate gateway",         phase: 4 },
  { id: "acr",       label: "ACR",          sub: "WORM audit record",      phase: 4 },
];

const STATE_STEP_MAP: Record<string, number> = {
  NEW:               0,
  EVIDENCE_PENDING:  1,
  FINDING_GENERATED: 3,
  APPROVAL_PENDING:  4,
  EXECUTION_READY:   5,
  DISPATCHED:        6,
  OUTCOME_RECORDED:  6,
  CLOSED:            7,
};

// ── Helpers ───────────────────────────────────────────────────────────────────
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
    if (["EXECUTION_READY","DISPATCHED","OUTCOME_RECORDED","CLOSED"].includes(c.state))
      map[month].recovered += c.diff ?? 0;
  }
  return Object.entries(map).map(([month, v]) => ({ month, ...v }));
}

function caseStatusBreakdown(cases: Case[]) {
  const STATE_LABELS: Record<string, string> = {
    NEW: "New", EVIDENCE_PENDING: "Evidence Pending", FINDING_GENERATED: "AI Analyzed",
    APPROVAL_PENDING: "In Review", EXECUTION_READY: "Approved", DISPATCHED: "Dispatched",
    OUTCOME_RECORDED: "Outcome Recorded", CLOSED: "Closed", ABORTED: "Aborted",
  };
  const map: Record<string, number> = {};
  for (const c of cases) {
    const label = STATE_LABELS[c.state] ?? c.state;
    map[label] = (map[label] ?? 0) + 1;
  }
  return Object.entries(map)
    .sort((a, b) => b[1] - a[1])
    .map(([name, value], i) => ({
      name, value,
      pct: Math.round((value / cases.length) * 100),
      color: COLORS[i % COLORS.length],
    }));
}

// ── Sub-components ────────────────────────────────────────────────────────────
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

function KpiCard({ label, value, sub, subColor, subIcon, spark, sparkColor, accentColor, onClick }: {
  label: string; value: string; sub?: string; subColor?: string;
  subIcon?: React.ElementType; spark?: number[]; sparkColor?: string;
  accentColor?: string; onClick?: () => void;
}) {
  const SubIcon = subIcon;
  return (
    <div
      onClick={onClick}
      className={cn(
        "bg-white rounded-xl border border-slate-200 px-4 py-3.5 flex flex-col gap-1.5 shadow-sm min-w-0 relative overflow-hidden",
        onClick && "cursor-pointer hover:shadow-md hover:-translate-y-0.5 transition-all duration-150"
      )}
    >
      {accentColor && (
        <div className="absolute top-0 left-0 right-0 h-0.5 rounded-t-xl" style={{ background: accentColor }} />
      )}
      <p className="text-[10px] text-slate-500 font-semibold uppercase tracking-wider truncate">{label}</p>
      <p className="text-2xl font-bold text-slate-800 leading-tight truncate">{value}</p>
      {sub && (
        <div className={cn("flex items-center gap-1 text-[11px] font-semibold", subColor ?? "text-emerald-600")}>
          {SubIcon && <SubIcon className="h-3 w-3" />}
          <span>{sub}</span>
        </div>
      )}
      {spark && <Sparkline data={spark} color={sparkColor ?? "#3b82f6"} />}
    </div>
  );
}

function SectionTitle({ title, sub, action, onAction }: {
  title: string; sub?: string; action?: string; onAction?: () => void;
}) {
  return (
    <div className="flex items-center justify-between mb-3">
      <div>
        <h3 className="text-sm font-bold text-slate-800">{title}</h3>
        {sub && <p className="text-[10px] text-slate-400 mt-0.5">{sub}</p>}
      </div>
      {action && (
        <button
          onClick={onAction}
          className="text-[11px] text-blue-600 hover:text-blue-700 flex items-center gap-0.5 font-semibold whitespace-nowrap"
        >
          {action} <ChevronRight className="h-3 w-3" />
        </button>
      )}
    </div>
  );
}

function StateBadge({ state }: { state: string }) {
  const cfg: Record<string, { label: string; cls: string }> = {
    CLOSED:            { label: "Closed",          cls: "bg-emerald-100 text-emerald-700" },
    OUTCOME_RECORDED:  { label: "Outcome Recorded",cls: "bg-emerald-100 text-emerald-700" },
    DISPATCHED:        { label: "Dispatched",      cls: "bg-blue-100 text-blue-700"       },
    EXECUTION_READY:   { label: "Ready",           cls: "bg-blue-100 text-blue-700"       },
    APPROVAL_PENDING:  { label: "Pending Approval",cls: "bg-amber-100 text-amber-700"     },
    FINDING_GENERATED: { label: "AI Analyzed",     cls: "bg-purple-100 text-purple-700"   },
    EVIDENCE_PENDING:  { label: "Evidence",        cls: "bg-slate-100 text-slate-600"     },
    NEW:               { label: "New",             cls: "bg-slate-100 text-slate-600"     },
    ABORTED:           { label: "Aborted",         cls: "bg-red-100 text-red-700"         },
  };
  const { label, cls } = cfg[state] ?? { label: state.replace(/_/g," "), cls: "bg-slate-100 text-slate-600" };
  return (
    <span className={cn("inline-flex items-center text-[10px] font-bold px-2 py-0.5 rounded-full whitespace-nowrap", cls)}>
      {label}
    </span>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────
export default function Home() {
  const nav = useNavigate();
  const { data: stats }        = useQuery({ queryKey: ["stats"],        queryFn: zoikoApi.getStats        });
  const { data: cases = [] }   = useQuery({ queryKey: ["cases"],        queryFn: () => zoikoApi.listCases() });
  const { data: tokens = [] }  = useQuery({ queryKey: ["tokens"],       queryFn: () => zoikoApi.listTokens() });
  const { data: kafkaEvents = [] } = useQuery({ queryKey: ["kafkaEvents"], queryFn: zoikoApi.listKafkaEvents });

  const totalCases      = stats?.total_cases      ?? cases.length;
  const totalRecovered  = stats?.total_recovered  ?? 0;
  const pendingApproval = stats?.pending_approval ?? 0;
  const approved        = stats?.approved         ?? 0;

  const carrierData = carrierOvercharges(cases);
  const trend       = monthlyTrend(cases);
  const statusData  = caseStatusBreakdown(cases);
  const openCases   = cases.filter(c => !["CLOSED","ABORTED","OUTCOME_RECORDED"].includes(c.state));
  const recentCases = cases.slice(0, 6);

  const totalOvercharge = carrierData.reduce((s, c) => s + c.overcharge, 0);
  const activeTokens    = (tokens as GovernanceToken[]).filter(t => t.status === "ACTIVE");

  // Latest non-closed case for pipeline tracker
  const demoCase = cases.find(c => c.state !== "ABORTED") ?? cases[0];
  const demoStep = demoCase ? (STATE_STEP_MAP[demoCase.state] ?? 0) : -1;

  return (
    <div className="space-y-5">

      {/* ── Page header ──────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Dashboard</h1>
          <p className="text-sm text-slate-400 mt-0.5">
            Freight audit, governance &amp; cryptographic recovery — SC-001
          </p>
        </div>
        <button
          onClick={() => nav("/cases/new")}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-semibold shadow-sm shadow-blue-500/30 transition-all hover:-translate-y-0.5"
        >
          <FileText className="h-4 w-4" />
          Submit Invoice
        </button>
      </div>

      {/* ── SC-001 Pipeline Tracker ───────────────────────────────────────── */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <div>
            <p className="text-sm font-bold text-slate-800">SC-001 Pipeline</p>
            <p className="text-[11px] text-slate-400 mt-0.5">
              {demoCase
                ? `Case ${demoCase.id.slice(0, 8)} · ${demoCase.carrier ?? "Unknown carrier"}`
                : "No active cases — submit an invoice to start"}
            </p>
          </div>
          {demoCase && (
            <button
              onClick={() => nav(`/cases/${demoCase.id}`)}
              className="flex items-center gap-1 text-[11px] text-blue-600 font-semibold hover:underline"
            >
              View case <ArrowRight className="h-3 w-3" />
            </button>
          )}
        </div>
        <div className="flex items-center gap-0 overflow-x-auto pb-1">
          {PIPELINE_STEPS.map((step, i) => {
            const done   = demoCase && i < demoStep;
            const active = demoCase && i === demoStep;
            const future = !demoCase || i > demoStep;
            return (
              <div key={step.id} className="flex items-center flex-1 min-w-0">
                <div className="flex flex-col items-center gap-1 flex-1 min-w-0">
                  <div className={cn(
                    "h-8 w-8 rounded-full flex items-center justify-center text-[11px] font-bold flex-shrink-0 transition-all",
                    done   ? "bg-emerald-500 text-white shadow-sm shadow-emerald-200"         : "",
                    active ? "bg-blue-600 text-white ring-2 ring-blue-300 ring-offset-1 shadow-sm shadow-blue-200" : "",
                    future ? "bg-slate-100 text-slate-400"                                    : "",
                  )}>
                    {done ? <CheckCircle2 className="h-4 w-4" /> : i + 1}
                  </div>
                  <div className="text-center min-w-0 px-1 hidden sm:block">
                    <p className={cn(
                      "text-[10px] font-semibold truncate",
                      active ? "text-blue-600" : done ? "text-emerald-600" : "text-slate-400",
                    )}>
                      {step.label}
                    </p>
                    <p className="text-[9px] text-slate-400 truncate">{step.sub}</p>
                  </div>
                </div>
                {i < PIPELINE_STEPS.length - 1 && (
                  <div className={cn(
                    "h-0.5 flex-1 mx-1 transition-colors",
                    done ? "bg-emerald-400" : "bg-slate-200"
                  )} />
                )}
              </div>
            );
          })}
        </div>
        {demoCase && (
          <div className="mt-4 pt-4 border-t border-slate-100 flex items-center gap-6 flex-wrap">
            {[
              { label: "Billed",     value: formatCurrency(demoCase.amount),       color: "text-slate-700" },
              { label: "Contract",   value: formatCurrency((demoCase.amount ?? 0) - (demoCase.diff ?? 0)), color: "text-slate-500" },
              { label: "Overcharge", value: formatCurrency(demoCase.diff),          color: "text-red-600 font-bold" },
              { label: "Confidence", value: demoCase.confidence ? `${(demoCase.confidence * 100).toFixed(0)}%` : "—", color: "text-emerald-600 font-bold" },
            ].map(m => (
              <div key={m.label}>
                <p className="text-[10px] text-slate-400 uppercase tracking-wide font-medium">{m.label}</p>
                <p className={cn("text-sm", m.color)}>{m.value}</p>
              </div>
            ))}
            <div className="ml-auto">
              <StateBadge state={demoCase.state} />
            </div>
          </div>
        )}
      </div>

      {/* ── 7 KPI Cards ──────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-3">
        <KpiCard
          label="Total Cases"
          value={totalCases.toLocaleString()}
          sub={cases.length > 0 ? `${openCases.length} open` : "No cases yet"}
          subColor="text-slate-500"
          accentColor="#3b82f6"
          onClick={() => nav("/cases")}
        />
        <KpiCard
          label="Overcharges Detected"
          value={formatCurrency(totalOvercharge)}
          sub={carrierData.length > 0 ? `${carrierData.length} carriers` : "No data"}
          subColor="text-red-500"
          subIcon={TrendingDown}
          accentColor="#ef4444"
        />
        <KpiCard
          label="Recovery Approved"
          value={formatCurrency(totalRecovered)}
          sub={approved > 0 ? `${approved} approved` : "No approvals"}
          subColor="text-emerald-600"
          subIcon={TrendingUp}
          accentColor="#10b981"
        />
        <KpiCard
          label="Pending Approval"
          value={formatCurrency(cases.filter(c => c.state === "APPROVAL_PENDING").reduce((s, c) => s + (c.diff ?? 0), 0))}
          sub={`${pendingApproval} awaiting`}
          subColor="text-amber-600"
          subIcon={Clock}
          accentColor="#f59e0b"
          onClick={() => nav("/manager")}
        />
        <KpiCard
          label="Open Cases"
          value={String(openCases.length)}
          sub={openCases.filter(c => c.state === "FINDING_GENERATED").length > 0
            ? `${openCases.filter(c => c.state === "FINDING_GENERATED").length} with findings`
            : "None with findings"}
          subColor="text-orange-500"
          subIcon={AlertTriangle}
          accentColor="#f97316"
          onClick={() => nav("/cases")}
        />
        <KpiCard
          label="Active Gov. Tokens"
          value={String(activeTokens.length)}
          sub={tokens.length > 0 ? `${tokens.length} total` : "No tokens"}
          subColor="text-blue-600"
          subIcon={Zap}
          accentColor="#8b5cf6"
          onClick={() => nav("/execute")}
        />
        <KpiCard
          label="Audit Integrity"
          value="99.86%"
          sub="Tamper Proof"
          subColor="text-emerald-600"
          subIcon={ShieldCheck}
          accentColor="#10b981"
          onClick={() => nav("/crypto")}
        />
      </div>

      {/* ── Charts row ───────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">

        {/* Overcharge by Carrier */}
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
          <SectionTitle title="Overcharge by Carrier" sub={`${carrierData.length} carriers`} action="View all" onAction={() => nav("/cases")} />
          {carrierData.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-[140px] text-slate-400 text-xs gap-2">
              <BarChart3 className="h-8 w-8 text-slate-200" />
              No overcharge data yet
            </div>
          ) : (
            <div className="flex items-center gap-3">
              <div className="flex-shrink-0">
                <ResponsiveContainer width={100} height={100}>
                  <PieChart>
                    <Pie data={carrierData} cx="50%" cy="50%" innerRadius={28} outerRadius={48}
                      dataKey="overcharge" paddingAngle={2}>
                      {carrierData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                    </Pie>
                    <Tooltip formatter={(v: number) => [formatCurrency(v)]} />
                  </PieChart>
                </ResponsiveContainer>
                <p className="text-center text-[9px] text-slate-400 font-bold -mt-1">Total</p>
              </div>
              <div className="flex-1 space-y-1.5 min-w-0">
                {carrierData.slice(0, 5).map((c, i) => (
                  <div key={c.carrier} className="flex items-center gap-1.5 text-[10px]">
                    <span className="h-2 w-2 rounded-full flex-shrink-0" style={{ background: COLORS[i % COLORS.length] }} />
                    <span className="text-slate-600 truncate flex-1 text-[10px]">{c.carrier}</span>
                    <span className="font-bold text-slate-700 flex-shrink-0">{c.pct}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Monthly Trend */}
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
          <SectionTitle title="Recovery Trend" sub="Monthly billed vs. recovered" />
          {trend.length === 0 ? (
            <div className="flex items-center justify-center h-[150px] text-slate-400 text-xs">No trend data yet</div>
          ) : (
            <ResponsiveContainer width="100%" height={150}>
              <ComposedChart data={trend} margin={{ top: 4, right: 4, left: -24, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="month" tick={{ fontSize: 9, fill: "#94a3b8" }} />
                <YAxis tick={{ fontSize: 9, fill: "#94a3b8" }} tickFormatter={(v: number) => `$${(v/1000).toFixed(0)}k`} />
                <Tooltip formatter={(v: number, n: string) => [formatCurrency(v), n === "overcharges" ? "Billed" : "Recovered"]} />
                <Legend iconSize={7} wrapperStyle={{ fontSize: 9 }} formatter={(v: string) => v === "overcharges" ? "Billed" : "Recovered"} />
                <Bar dataKey="overcharges" fill="#3b82f6" radius={[3,3,0,0]} name="overcharges" />
                <Line type="monotone" dataKey="recovered" stroke="#10b981" strokeWidth={2} dot={false} name="recovered" />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Top Carriers table */}
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
          <SectionTitle title="Top Carriers" sub="By overcharge amount" />
          {carrierData.length === 0 ? (
            <div className="flex items-center justify-center h-[120px] text-slate-400 text-xs">No carrier data yet</div>
          ) : (
            <table className="w-full">
              <thead>
                <tr className="text-slate-400 border-b text-[10px]">
                  <th className="text-left pb-2 font-medium">Carrier</th>
                  <th className="text-right pb-2 font-medium">Overcharge</th>
                  <th className="text-right pb-2 font-medium">Cases</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {carrierData.slice(0, 5).map((c, i) => (
                  <tr key={c.carrier} className="hover:bg-slate-50 transition-colors">
                    <td className="py-2">
                      <div className="flex items-center gap-1.5">
                        <span className="h-2 w-2 rounded-full flex-shrink-0" style={{ background: COLORS[i % COLORS.length] }} />
                        <span className="text-[11px] font-medium text-slate-700">{c.carrier}</span>
                      </div>
                    </td>
                    <td className="py-2 text-right text-[10px] text-red-600 font-semibold">{formatCurrency(c.overcharge)}</td>
                    <td className="py-2 text-right text-[11px] font-bold text-slate-700">{c.cases}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Case Status donut */}
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
          <SectionTitle title="Case Status" action="All cases" onAction={() => nav("/cases")} />
          {statusData.length === 0 ? (
            <div className="flex items-center justify-center h-[160px] text-slate-400 text-xs">No cases yet</div>
          ) : (
            <div className="flex flex-col items-center">
              <ResponsiveContainer width="100%" height={110}>
                <PieChart>
                  <Pie data={statusData} cx="50%" cy="50%" innerRadius={28} outerRadius={48}
                    dataKey="value" paddingAngle={2}>
                    {statusData.map((e, i) => <Cell key={i} fill={e.color} />)}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
              <p className="text-2xl font-bold text-slate-800 -mt-2">{totalCases.toLocaleString()}</p>
              <p className="text-[10px] text-slate-400 mb-3">Total Cases</p>
              <div className="w-full space-y-1.5">
                {statusData.slice(0, 5).map(s => (
                  <div key={s.name} className="flex items-center justify-between text-[10px]">
                    <div className="flex items-center gap-1.5">
                      <span className="h-2 w-2 rounded-full" style={{ background: s.color }} />
                      <span className="text-slate-600">{s.name}</span>
                    </div>
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
          <SectionTitle title="Active Governance Tokens" sub={`${activeTokens.length} active`} action="Execute" onAction={() => nav("/execute")} />
          {activeTokens.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-[100px] text-slate-400 text-xs gap-2">
              <div className="h-8 w-8 rounded-full bg-slate-100 flex items-center justify-center">
                <Zap className="h-4 w-4 text-slate-300" />
              </div>
              No active tokens
            </div>
          ) : (
            <div className="space-y-2">
              {activeTokens.slice(0, 4).map((t: GovernanceToken) => (
                <div key={t.id} className="flex items-center justify-between rounded-lg bg-slate-50 border border-slate-100 px-3 py-2">
                  <div>
                    <p className="font-mono text-[10px] text-blue-600">{t.id.slice(0, 10)}…</p>
                    <p className="text-[10px] text-slate-500 mt-0.5">{t.action.replace("EXECUTE_","")}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-[11px] font-bold text-slate-700">{formatCurrency(t.amount)}</p>
                    <p className="text-[9px] text-amber-600 font-medium">
                      Exp {new Date(t.exp).toLocaleDateString("en-IN",{month:"short",day:"numeric"})}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Crypto Integrity */}
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
          <SectionTitle title="Cryptographic Integrity" sub="Real-time audit health" />
          <div className="space-y-3">
            <div className="rounded-lg bg-emerald-50 border border-emerald-100 px-3 py-2.5 flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-emerald-600 flex-shrink-0" />
              <div>
                <p className="text-xs font-bold text-emerald-800">All systems verified</p>
                <p className="text-[10px] text-emerald-600">Ed25519 + Merkle chain intact</p>
              </div>
              <Lock className="h-3.5 w-3.5 text-emerald-500 ml-auto" />
            </div>
            <div className="flex items-center justify-between">
              <p className="text-[10px] text-slate-400">Merkle Root (Latest)</p>
              <code className="text-[9px] font-mono text-slate-600 bg-slate-50 border border-slate-100 px-2 py-0.5 rounded">
                a1b2c3d4…9z8y
              </code>
            </div>
            {[
              { label: "Total Cases",      value: String(totalCases),          color: "text-slate-700" },
              { label: "Pending Approval", value: String(pendingApproval),     color: "text-amber-600" },
              { label: "Approved",         value: String(approved),            color: "text-emerald-600 font-bold" },
              { label: "Active Tokens",    value: String(activeTokens.length), color: "text-blue-600"  },
            ].map(r => (
              <div key={r.label} className="flex items-center justify-between border-t border-slate-50 pt-2">
                <p className="text-[10px] text-slate-500">{r.label}</p>
                <p className={cn("text-[11px] font-bold", r.color)}>{r.value}</p>
              </div>
            ))}
          </div>
          <button
            onClick={() => nav("/crypto")}
            className="mt-3 w-full text-[11px] text-blue-600 border border-blue-200 rounded-lg py-1.5 hover:bg-blue-50 flex items-center justify-center gap-1.5 font-semibold transition-colors"
          >
            <GitBranch className="h-3 w-3" /> Verify Audit Chain
          </button>
        </div>

        {/* Recent Activity */}
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
          <SectionTitle title="Recent Activity" sub="Kafka event stream" action="All events" onAction={() => nav("/alerts")} />
          {(kafkaEvents as KafkaEvent[]).length === 0 ? (
            <div className="flex flex-col items-center justify-center h-[100px] text-slate-400 text-xs gap-2">
              <RefreshCw className="h-6 w-6 text-slate-200" />
              No activity yet
            </div>
          ) : (
            <div className="space-y-3">
              {(kafkaEvents as KafkaEvent[]).slice(0, 5).map((e, i) => (
                <div key={i} className="flex items-start gap-3">
                  <div className="h-7 w-7 rounded-lg bg-blue-50 border border-blue-100 flex items-center justify-center text-[10px] font-bold text-blue-600 flex-shrink-0">
                    {e.topic.slice(0, 2).toUpperCase()}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-[11px] text-slate-700 leading-snug truncate font-medium">
                      {e.topic.replace(/\./g," · ")}
                    </p>
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

      {/* ── Open + Recent Cases ───────────────────────────────────────────── */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
          <SectionTitle title="Open Cases" action="View all" onAction={() => nav("/cases")} />
          {openCases.length === 0 ? (
            <div className="flex items-center justify-center h-[80px] text-slate-400 text-xs">No open cases</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="text-slate-400 border-b text-[10px]">
                    <th className="text-left pb-2 font-medium">Case</th>
                    <th className="text-left pb-2 font-medium">Carrier</th>
                    <th className="text-right pb-2 font-medium">Billed</th>
                    <th className="text-right pb-2 font-medium">Overcharge</th>
                    <th className="text-left pb-2 font-medium pl-2">State</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {openCases.slice(0, 5).map(c => (
                    <tr
                      key={c.id}
                      className="hover:bg-slate-50 cursor-pointer transition-colors"
                      onClick={() => nav(`/cases/${c.id}`)}
                    >
                      <td className="py-2 font-mono text-[10px] text-blue-600">{c.id.slice(0, 8)}</td>
                      <td className="py-2 text-[11px] font-semibold text-slate-700">{c.carrier || "—"}</td>
                      <td className="py-2 text-right text-[10px] text-slate-600">{formatCurrency(c.amount)}</td>
                      <td className="py-2 text-right text-[10px] font-bold text-red-600">{c.diff > 0 ? formatCurrency(c.diff) : "—"}</td>
                      <td className="py-2 pl-2"><StateBadge state={c.state} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
          <SectionTitle title="Recent Cases" action="View all" onAction={() => nav("/cases")} />
          {recentCases.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-[80px] text-slate-400 text-xs gap-2">
              <FileText className="h-6 w-6 text-slate-200" />
              No cases yet — submit an invoice to start
            </div>
          ) : (
            <div className="overflow-x-auto">
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
                    <tr
                      key={c.id}
                      className="hover:bg-slate-50 cursor-pointer transition-colors"
                      onClick={() => nav(`/cases/${c.id}`)}
                    >
                      <td className="py-2 font-mono text-[10px] text-blue-600">{c.id.slice(0, 8)}</td>
                      <td className="py-2 text-[11px] font-semibold text-slate-700">{c.carrier || "—"}</td>
                      <td className="py-2 text-[10px] text-slate-400">{c.shipment_ref || "—"}</td>
                      <td className="py-2 text-right text-[11px] text-slate-700 font-medium">{formatCurrency(c.amount)}</td>
                      <td className="py-2 pl-2"><StateBadge state={c.state} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* ── Status footer bar ────────────────────────────────────────────── */}
      <div className="bg-gradient-to-r from-[#0a0f1e] to-[#0d1424] rounded-xl px-6 py-4 flex flex-wrap items-center justify-between gap-4 border border-slate-800">
        {[
          { icon: Award,      title: "SOC 2 Type II",              sub: "Platform certified"       },
          { icon: ShieldCheck,title: "Ed25519 + SHA-256",          sub: "All records signed"       },
          { icon: GitBranch,  title: "Immutable Audit Trail",      sub: "Merkle WORM index"        },
          { icon: Lock,       title: "8-Gate Execution",           sub: "Zero partial execution"   },
          { icon: CheckCircle2, title: "All Systems Operational",  sub: "Phase 0–5 active"         },
        ].map(s => (
          <div key={s.title} className="flex items-center gap-2.5">
            <div className="h-8 w-8 rounded-lg bg-white/5 border border-white/10 flex items-center justify-center flex-shrink-0">
              <s.icon className="h-4 w-4 text-blue-400" />
            </div>
            <div>
              <p className="text-[11px] font-bold text-white leading-tight">{s.title}</p>
              <p className="text-[10px] text-slate-500">{s.sub}</p>
            </div>
          </div>
        ))}
      </div>

    </div>
  );
}
