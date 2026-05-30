import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { zoikoApi } from "@/api/zoiko";
import { formatCurrency, formatDate, cn } from "@/utils/cn";
import { Search, Plus, Filter, ChevronRight, ArrowUpDown, FileText } from "lucide-react";
import type { CaseState } from "@/types";

const STATE_TABS: (CaseState | "ALL")[] = [
  "ALL",
  "FINDING_GENERATED",
  "APPROVAL_PENDING",
  "EXECUTION_READY",
  "DISPATCHED",
  "CLOSED",
  "ABORTED",
];

const STATE_CONFIG: Record<string, { label: string; cls: string; dot: string }> = {
  NEW:               { label: "New",             cls: "bg-slate-100 text-slate-600",    dot: "bg-slate-400"  },
  EVIDENCE_PENDING:  { label: "Evidence",        cls: "bg-slate-100 text-slate-600",    dot: "bg-slate-400"  },
  FINDING_GENERATED: { label: "AI Analyzed",     cls: "bg-purple-100 text-purple-700",  dot: "bg-purple-500" },
  APPROVAL_PENDING:  { label: "Pending Approval",cls: "bg-amber-100 text-amber-700",    dot: "bg-amber-500"  },
  EXECUTION_READY:   { label: "Ready",           cls: "bg-blue-100 text-blue-700",      dot: "bg-blue-500"   },
  DISPATCHED:        { label: "Dispatched",      cls: "bg-emerald-100 text-emerald-700",dot: "bg-emerald-500"},
  OUTCOME_RECORDED:  { label: "Outcome Recorded",cls: "bg-emerald-100 text-emerald-700",dot: "bg-emerald-500"},
  CLOSED:            { label: "Closed",          cls: "bg-slate-100 text-slate-500",    dot: "bg-slate-400"  },
  ABORTED:           { label: "Aborted",         cls: "bg-red-100 text-red-700",        dot: "bg-red-500"    },
};

function StateBadge({ state }: { state: string }) {
  const cfg = STATE_CONFIG[state] ?? { label: state, cls: "bg-slate-100 text-slate-600", dot: "bg-slate-400" };
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-[10px] font-bold px-2.5 py-1 rounded-full whitespace-nowrap", cfg.cls)}>
      <span className={cn("h-1.5 w-1.5 rounded-full", cfg.dot)} />
      {cfg.label}
    </span>
  );
}

function ConfidenceBadge({ value }: { value: number | null }) {
  if (value === null || value === undefined) return <span className="text-slate-300">—</span>;
  const pct = Math.round(value * 100);
  const cls = pct >= 90 ? "text-emerald-600 bg-emerald-50" : pct >= 70 ? "text-amber-600 bg-amber-50" : "text-red-600 bg-red-50";
  return (
    <span className={cn("text-[11px] font-bold px-2 py-0.5 rounded-md", cls)}>
      {pct}%
    </span>
  );
}

export default function Cases() {
  const nav = useNavigate();
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<CaseState | "ALL">("ALL");
  const { data: cases, isLoading } = useQuery({
    queryKey: ["cases"],
    queryFn:  () => zoikoApi.listCases(),
    refetchInterval: 5000,   // spec: poll active cases every 5s
  });

  const filtered = (cases || [])
    .filter(c => filter === "ALL" || c.state === filter)
    .filter(c => !search || c.id.includes(search) || (c.carrier ?? "").toLowerCase().includes(search.toLowerCase()) || (c.shipment_ref ?? "").toLowerCase().includes(search.toLowerCase()));

  const byState = (cases || []).reduce<Record<string, number>>((acc, c) => {
    acc[c.state] = (acc[c.state] ?? 0) + 1;
    return acc;
  }, {});

  const tabLabel = (s: CaseState | "ALL") => {
    if (s === "ALL") return `All (${cases?.length ?? 0})`;
    const cfg = STATE_CONFIG[s];
    const count = byState[s] ?? 0;
    return `${cfg?.label ?? s} (${count})`;
  };

  return (
    <div className="space-y-5">

      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Cases</h1>
          <p className="text-sm text-slate-400 mt-0.5">
            {cases?.length ?? 0} total · {(cases || []).filter(c => !["CLOSED","ABORTED"].includes(c.state)).length} open
          </p>
        </div>
        <button
          onClick={() => nav("/cases/new")}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-semibold shadow-sm shadow-blue-500/25 transition-all hover:-translate-y-0.5"
        >
          <Plus className="h-4 w-4" />
          Submit Invoice
        </button>
      </div>

      {/* ── Summary tiles ──────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: "Pending Approval", value: byState["APPROVAL_PENDING"] ?? 0, color: "border-l-amber-400 text-amber-700" },
          { label: "AI Analyzed",      value: byState["FINDING_GENERATED"] ?? 0,color: "border-l-purple-400 text-purple-700"},
          { label: "Dispatched",       value: (byState["DISPATCHED"] ?? 0) + (byState["OUTCOME_RECORDED"] ?? 0), color: "border-l-emerald-400 text-emerald-700" },
          { label: "Closed",           value: byState["CLOSED"] ?? 0,           color: "border-l-slate-400 text-slate-600"  },
        ].map(t => (
          <div key={t.label} className={cn("bg-white rounded-xl border border-slate-200 border-l-4 px-4 py-3 shadow-sm", t.color.split(" ")[0])}>
            <p className="text-[10px] text-slate-500 font-semibold uppercase tracking-wide">{t.label}</p>
            <p className={cn("text-2xl font-bold mt-1", t.color.split(" ")[1])}>{t.value}</p>
          </div>
        ))}
      </div>

      {/* ── Filters ────────────────────────────────────────────────────── */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">

        {/* Search + filter bar */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-slate-100">
          <div className="relative flex-1 max-w-xs">
            <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              className="pl-9 pr-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/30 w-full"
              placeholder="Search by ID, carrier, shipment…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
          <button className="flex items-center gap-1.5 px-3 py-2 border border-slate-200 rounded-lg text-sm text-slate-600 hover:bg-slate-50 transition-colors">
            <Filter className="h-3.5 w-3.5" /> Filter
          </button>
          <button className="flex items-center gap-1.5 px-3 py-2 border border-slate-200 rounded-lg text-sm text-slate-600 hover:bg-slate-50 transition-colors">
            <ArrowUpDown className="h-3.5 w-3.5" /> Sort
          </button>
        </div>

        {/* State tabs */}
        <div className="flex gap-0 overflow-x-auto border-b border-slate-100 px-4 scrollbar-thin">
          {STATE_TABS.map(s => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={cn(
                "flex-shrink-0 px-3 py-2.5 text-[11px] font-semibold border-b-2 transition-colors whitespace-nowrap",
                filter === s
                  ? "border-blue-500 text-blue-600"
                  : "border-transparent text-slate-500 hover:text-slate-700"
              )}
            >
              {tabLabel(s)}
            </button>
          ))}
        </div>

        {/* Table */}
        {isLoading ? (
          <div className="divide-y divide-slate-50">
            {[0,1,2,3,4].map(i => (
              <div key={i} className="flex items-center gap-4 px-5 py-4 animate-pulse">
                <div className="h-3 w-20 bg-slate-100 rounded-full" />
                <div className="h-3 w-24 bg-slate-100 rounded-full" />
                <div className="h-3 w-32 bg-slate-100 rounded-full" />
                <div className="h-3 w-16 bg-slate-100 rounded-full ml-auto" />
                <div className="h-5 w-20 bg-slate-100 rounded-full" />
              </div>
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-slate-400 gap-3">
            <div className="h-12 w-12 rounded-full bg-slate-100 flex items-center justify-center">
              <FileText className="h-6 w-6 text-slate-300" />
            </div>
            <div className="text-center">
              <p className="font-semibold text-slate-600 text-sm">No cases found</p>
              <p className="text-xs mt-1">Try adjusting your search or filter</p>
            </div>
          </div>
        ) : (
          <>
            {/* Column headers */}
            <div className="grid grid-cols-[1fr_1fr_1.5fr_1fr_1fr_1fr_1.5fr_auto] items-center gap-4 px-5 py-2 bg-slate-50 text-[10px] font-semibold uppercase tracking-wide text-slate-400 border-b border-slate-100">
              <span>Case ID</span>
              <span>Carrier</span>
              <span>Shipment</span>
              <span className="text-right">Amount</span>
              <span className="text-right">Overcharge</span>
              <span>AI Score</span>
              <span>State</span>
              <span />
            </div>
            <div className="divide-y divide-slate-50">
              {filtered.map(c => (
                <div
                  key={c.id}
                  onClick={() => nav(`/cases/${c.id}`)}
                  className="grid grid-cols-[1fr_1fr_1.5fr_1fr_1fr_1fr_1.5fr_auto] items-center gap-4 px-5 py-3.5 hover:bg-slate-50 cursor-pointer transition-colors group"
                >
                  <code className="text-[11px] text-blue-600 font-mono truncate">
                    {c.id.slice(0, 8)}
                  </code>
                  <span className="text-[12px] font-semibold text-slate-700 truncate">{c.carrier || "—"}</span>
                  <span className="text-[11px] text-slate-400 truncate">{c.shipment_ref || "—"}</span>
                  <span className="text-right text-[11px] text-slate-600 font-medium">{formatCurrency(c.amount, c.currency)}</span>
                  <span className={cn("text-right text-[11px] font-bold", c.diff > 0 ? "text-red-600" : "text-slate-400")}>
                    {c.diff > 0 ? formatCurrency(c.diff, c.currency) : "—"}
                  </span>
                  <span><ConfidenceBadge value={c.confidence ?? null} /></span>
                  <span><StateBadge state={c.state} /></span>
                  <ChevronRight className="h-4 w-4 text-slate-300 group-hover:text-slate-500 transition-colors" />
                </div>
              ))}
            </div>
          </>
        )}

        {/* Footer count */}
        {!isLoading && filtered.length > 0 && (
          <div className="px-5 py-3 border-t border-slate-100 text-[10px] text-slate-400 flex items-center justify-between">
            <span>Showing {filtered.length} of {cases?.length ?? 0} cases</span>
            <span className="text-[10px] text-slate-300">Last updated: just now</span>
          </div>
        )}
      </div>
    </div>
  );
}
