import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { zoikoApi } from "@/api/zoiko";
import { formatCurrency } from "@/utils/cn";
import { MessageSquare, ChevronRight, DollarSign, TrendingUp, AlertCircle } from "lucide-react";
import type { Case } from "@/types";

const DISPUTE_STATES = ["APPROVAL_PENDING", "EXECUTION_READY", "DISPATCHED", "OUTCOME_RECORDED", "CLOSED", "ABORTED"];

const FILTER_OPTIONS = [
  { value: "ALL",              label: "All"             },
  { value: "APPROVAL_PENDING", label: "Pending Approval"},
  { value: "EXECUTION_READY",  label: "Ready"           },
  { value: "DISPATCHED",       label: "Dispatched"      },
  { value: "CLOSED",           label: "Resolved"        },
  { value: "ABORTED",          label: "Rejected"        },
];

const STATUS_BADGE: Record<string, { label: string; cls: string }> = {
  APPROVAL_PENDING: { label: "pending approval", cls: "bg-[#fef3c7] text-[#d97706]" },
  EXECUTION_READY:  { label: "ready",            cls: "bg-[#dbeafe] text-[#2563eb]" },
  DISPATCHED:       { label: "dispatched",       cls: "bg-[#dcfce7] text-[#16a34a]" },
  OUTCOME_RECORDED: { label: "resolved",         cls: "bg-[#dcfce7] text-[#16a34a]" },
  CLOSED:           { label: "resolved",         cls: "bg-[#dcfce7] text-[#16a34a]" },
  ABORTED:          { label: "rejected",         cls: "bg-[#fee2e2] text-[#dc2626]" },
};

function StatusBadge({ state }: { state: string }) {
  const s = STATUS_BADGE[state] ?? { label: state.toLowerCase(), cls: "bg-[#f1f5f9] text-[#64748b]" };
  return (
    <span className={`inline-block text-[10px] font-bold px-2.5 py-1 rounded-full whitespace-nowrap ${s.cls}`}>
      {s.label}
    </span>
  );
}

export default function DisputesPage() {
  const nav = useNavigate();
  const [filter, setFilter] = useState("ALL");

  const { data: cases = [], isLoading } = useQuery({
    queryKey: ["cases"],
    queryFn:  () => zoikoApi.listCases(),
    refetchInterval: 8000,
  });

  const allCases   = cases as Case[];
  const disputes   = allCases.filter(c => DISPUTE_STATES.includes(c.state));
  const filtered   = filter === "ALL" ? disputes : disputes.filter(c => c.state === filter);

  const totalDisputed  = disputes.reduce((s, c) => s + (c.diff ?? 0), 0);
  const totalRecovered = allCases
    .filter(c => ["DISPATCHED","OUTCOME_RECORDED","CLOSED"].includes(c.state))
    .reduce((s, c) => s + (c.diff ?? 0), 0);
  const openCount = disputes.filter(c => ["APPROVAL_PENDING","EXECUTION_READY"].includes(c.state)).length;

  const fmtDate = (iso: string) =>
    new Date(iso).toLocaleDateString("en-IN", { month: "short", day: "numeric", year: "numeric" });

  return (
    <div className="space-y-5">

      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div>
        <h1 className="text-[22px] font-extrabold text-[#1e293b]">Dispute Letters</h1>
        <p className="text-[13px] text-slate-500 mt-0.5">Track all carrier dispute letters and their resolution status.</p>
      </div>

      {/* ── KPI tiles ───────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white rounded-xl border border-[#e8edf2] p-5 shadow-[0_1px_3px_rgba(0,0,0,0.06)]">
          <p className="text-[10px] font-bold uppercase tracking-widest text-[#94a3b8] mb-3">Total Disputes</p>
          <p className="text-[26px] font-extrabold text-[#1e293b] leading-none">{disputes.length}</p>
        </div>
        <div className="bg-white rounded-xl border border-[#e8edf2] p-5 shadow-[0_1px_3px_rgba(0,0,0,0.06)]">
          <p className="text-[10px] font-bold uppercase tracking-widest text-[#94a3b8] mb-3">Total Disputed</p>
          <p className="text-[26px] font-extrabold text-red-600 leading-none">{formatCurrency(totalDisputed)}</p>
        </div>
        <div className="bg-white rounded-xl border border-[#e8edf2] p-5 shadow-[0_1px_3px_rgba(0,0,0,0.06)]">
          <p className="text-[10px] font-bold uppercase tracking-widest text-[#94a3b8] mb-3">Total Recovered</p>
          <p className="text-[26px] font-extrabold text-[#16a34a] leading-none">{formatCurrency(totalRecovered)}</p>
        </div>
        <div className="bg-white rounded-xl border border-[#e8edf2] p-5 shadow-[0_1px_3px_rgba(0,0,0,0.06)]">
          <p className="text-[10px] font-bold uppercase tracking-widest text-[#94a3b8] mb-3">Open Disputes</p>
          <p className="text-[26px] font-extrabold text-[#2563eb] leading-none">{openCount}</p>
        </div>
      </div>

      {/* ── Filter ──────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3">
        <div className="relative">
          <select
            value={filter}
            onChange={e => setFilter(e.target.value)}
            className="appearance-none bg-white border border-[#e2e8f0] rounded-lg pl-3 pr-8 py-2.5 text-[13px] text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500/20 cursor-pointer"
          >
            {FILTER_OPTIONS.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          <ChevronRight className="absolute right-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400 rotate-90 pointer-events-none" />
        </div>
      </div>

      {/* ── Table card ──────────────────────────────────────────────────── */}
      <div className="bg-white rounded-xl border border-[#e2e8f0] shadow-[0_1px_3px_rgba(0,0,0,0.06)] overflow-hidden">

        {isLoading ? (
          <div className="divide-y divide-[#f8fafc]">
            {[1,2,3].map(i => (
              <div key={i} className="px-5 py-4 flex items-center gap-4 animate-pulse">
                <div className="flex-1 space-y-1.5">
                  <div className="h-3 w-36 bg-slate-100 rounded" />
                  <div className="h-2.5 w-24 bg-slate-100 rounded" />
                </div>
                <div className="h-3 w-20 bg-slate-100 rounded" />
                <div className="h-5 w-28 bg-slate-100 rounded-full" />
              </div>
            ))}
          </div>

        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 gap-3">
            <MessageSquare className="h-12 w-12 text-slate-200" />
            <div className="text-center">
              <p className="text-[14px] font-bold text-[#374151]">No dispute letters yet</p>
              <p className="text-[12px] text-slate-400 mt-1">Disputes are auto-generated when billing errors are found in your invoices.</p>
            </div>
          </div>

        ) : (
          <>
            <div className="grid grid-cols-[2fr_1fr_1fr_1.2fr_auto] items-center gap-4 px-5 py-3 border-b border-[#f1f5f9]">
              {["Carrier / Invoice", "Date", "Overcharge", "Status", ""].map(h => (
                <span key={h} className="text-[10px] font-bold uppercase tracking-widest text-[#94a3b8]">{h}</span>
              ))}
            </div>
            <div className="divide-y divide-[#f8fafc]">
              {filtered.map((c: Case) => (
                <div
                  key={c.id}
                  onClick={() => nav(`/cases/${c.id}`)}
                  className="grid grid-cols-[2fr_1fr_1fr_1.2fr_auto] items-center gap-4 px-5 py-4 hover:bg-[#fafbfc] cursor-pointer transition-colors"
                >
                  <div>
                    <p className="text-[13px] font-bold text-[#1e293b]">{c.carrier || "Unknown Carrier"}</p>
                    <p className="text-[11px] text-slate-400 mt-0.5 font-mono">{c.id.slice(0, 8).toUpperCase()}</p>
                  </div>
                  <span className="text-[12px] text-slate-600">{fmtDate(c.opened_at)}</span>
                  <span className="text-[13px] font-bold text-red-600">
                    {(c.diff ?? 0) > 0 ? formatCurrency(c.diff, c.currency) : "—"}
                  </span>
                  <StatusBadge state={c.state} />
                  <ChevronRight className="h-4 w-4 text-slate-300" />
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
