import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { zoikoApi } from "@/api/zoiko";
import { cn } from "@/utils/cn";
import { Search, Plus, ChevronRight, AlertTriangle } from "lucide-react";
import type { ExceptionState } from "@/types";

const STATE_TABS: (ExceptionState | "ALL")[] = [
  "ALL", "FINDING_GENERATED", "APPROVAL_PENDING",
  "EXECUTION_READY", "DISPATCHED", "CLOSED", "ABORTED",
];

const STATE_CONFIG: Record<string, { label: string; cls: string; dot: string }> = {
  NEW:               { label: "New",              cls: "bg-slate-100 text-slate-600",     dot: "bg-slate-400"  },
  EVIDENCE_PENDING:  { label: "Evidence",         cls: "bg-slate-100 text-slate-600",     dot: "bg-slate-400"  },
  FINDING_GENERATED: { label: "AI Analyzed",      cls: "bg-purple-100 text-purple-700",   dot: "bg-purple-500" },
  APPROVAL_PENDING:  { label: "Pending Approval", cls: "bg-amber-100 text-amber-700",     dot: "bg-amber-500"  },
  EXECUTION_READY:   { label: "Ready",            cls: "bg-blue-100 text-blue-700",       dot: "bg-blue-500"   },
  DISPATCHED:        { label: "Dispatched",       cls: "bg-emerald-100 text-emerald-700", dot: "bg-emerald-500"},
  OUTCOME_RECORDED:  { label: "Outcome Recorded", cls: "bg-emerald-100 text-emerald-700", dot: "bg-emerald-500"},
  CLOSED:            { label: "Closed",           cls: "bg-slate-100 text-slate-500",     dot: "bg-slate-400"  },
  ABORTED:           { label: "Aborted",          cls: "bg-red-100 text-red-700",         dot: "bg-red-500"    },
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

function BreachBadge({ hours }: { hours: number }) {
  const cls = hours >= 24 ? "text-red-600 bg-red-50" : hours >= 4 ? "text-amber-600 bg-amber-50" : "text-emerald-600 bg-emerald-50";
  return (
    <span className={cn("text-[11px] font-bold px-2 py-0.5 rounded-md", cls)}>
      {hours.toFixed(1)}h
    </span>
  );
}

function ConfidenceBadge({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) return <span className="text-slate-300">—</span>;
  const pct = Math.round(value * 100);
  const cls = pct >= 90 ? "text-emerald-600 bg-emerald-50" : pct >= 70 ? "text-amber-600 bg-amber-50" : "text-red-600 bg-red-50";
  return <span className={cn("text-[11px] font-bold px-2 py-0.5 rounded-md", cls)}>{pct}%</span>;
}

function fmt(n: number, currency = "INR") {
  return new Intl.NumberFormat("en-IN", { style: "currency", currency, maximumFractionDigits: 0 }).format(n);
}

export default function Exceptions() {
  const nav = useNavigate();
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<ExceptionState | "ALL">("ALL");
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 50;

  const { data: paged, isLoading } = useQuery({
    queryKey: ["exceptions", filter, page],
    queryFn:  () => zoikoApi.listExceptionsPaged({ state: filter === "ALL" ? undefined : filter, page, page_size: PAGE_SIZE }),
    refetchInterval: 15_000,
  });

  const exceptions = paged?.exceptions ?? [];
  const total      = paged?.total ?? 0;
  const pages      = paged?.pages ?? 1;

  const filtered = search.trim()
    ? exceptions.filter(e =>
        e.shipment_reference.toLowerCase().includes(search.toLowerCase()) ||
        (e.carrier ?? "").toLowerCase().includes(search.toLowerCase())
      )
    : exceptions;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Shipment Exceptions</h1>
          <p className="text-xs text-slate-500 mt-0.5">SLA breach detection &amp; penalty recovery · SC-003</p>
        </div>
        <button
          onClick={() => nav("/exceptions/new")}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700 transition-colors"
        >
          <Plus className="h-4 w-4" /> Report Exception
        </button>
      </div>

      {/* State tabs */}
      <div className="flex gap-1 flex-wrap">
        {STATE_TABS.map(tab => (
          <button
            key={tab}
            onClick={() => { setFilter(tab); setPage(1); }}
            className={cn(
              "px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors",
              filter === tab
                ? "bg-blue-600 text-white"
                : "bg-white border border-slate-200 text-slate-600 hover:border-slate-300 hover:bg-slate-50"
            )}
          >
            {tab === "ALL" ? "All" : STATE_CONFIG[tab]?.label ?? tab}
          </button>
        ))}
      </div>

      {/* Search + count */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
          <input
            value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Search shipment reference or carrier…"
            className="pl-9 pr-3 py-2 border border-slate-200 rounded-lg text-sm w-full focus:outline-none focus:ring-2 focus:ring-blue-500/30 bg-white"
          />
        </div>
        <span className="text-xs text-slate-500">{total} exception{total !== 1 ? "s" : ""}</span>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
        {isLoading ? (
          <div className="py-16 text-center text-slate-400 text-sm">Loading exceptions…</div>
        ) : filtered.length === 0 ? (
          <div className="py-16 text-center">
            <AlertTriangle className="h-8 w-8 text-slate-300 mx-auto mb-2" />
            <p className="text-slate-500 text-sm">No shipment exceptions found</p>
            <p className="text-slate-400 text-xs mt-1">Report a new exception to get started</p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 bg-slate-50 text-left">
                <th className="px-4 py-3 text-[11px] font-bold text-slate-500 uppercase tracking-wide">Shipment Ref</th>
                <th className="px-4 py-3 text-[11px] font-bold text-slate-500 uppercase tracking-wide">Carrier</th>
                <th className="px-4 py-3 text-[11px] font-bold text-slate-500 uppercase tracking-wide">Breach</th>
                <th className="px-4 py-3 text-[11px] font-bold text-slate-500 uppercase tracking-wide">Penalty</th>
                <th className="px-4 py-3 text-[11px] font-bold text-slate-500 uppercase tracking-wide">Confidence</th>
                <th className="px-4 py-3 text-[11px] font-bold text-slate-500 uppercase tracking-wide">State</th>
                <th className="px-4 py-3 text-[11px] font-bold text-slate-500 uppercase tracking-wide">Opened</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {filtered.map(exc => (
                <tr
                  key={exc.id}
                  onClick={() => nav(`/exceptions/${exc.id}`)}
                  className="hover:bg-slate-50 cursor-pointer transition-colors"
                >
                  <td className="px-4 py-3 font-mono text-xs text-slate-700 font-semibold">
                    {exc.shipment_reference}
                  </td>
                  <td className="px-4 py-3 text-slate-700 font-medium">{exc.carrier || exc.carrier_id || "—"}</td>
                  <td className="px-4 py-3">
                    <BreachBadge hours={exc.sla_breach_hours ?? 0} />
                  </td>
                  <td className="px-4 py-3 text-slate-700 font-semibold tabular-nums">
                    {fmt(exc.sla_penalty_amount ?? 0, exc.currency)}
                  </td>
                  <td className="px-4 py-3">
                    <ConfidenceBadge value={exc.confidence} />
                  </td>
                  <td className="px-4 py-3">
                    <StateBadge state={exc.state} />
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-400">
                    {new Date(exc.opened_at).toLocaleDateString("en-IN")}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <ChevronRight className="h-4 w-4 text-slate-300 inline" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {pages > 1 && (
        <div className="flex items-center justify-between text-xs text-slate-500">
          <span>Page {page} of {pages}</span>
          <div className="flex gap-2">
            <button
              disabled={page <= 1}
              onClick={() => setPage(p => p - 1)}
              className="px-3 py-1.5 bg-white border border-slate-200 rounded-lg disabled:opacity-40 hover:bg-slate-50 transition-colors"
            >← Prev</button>
            <button
              disabled={page >= pages}
              onClick={() => setPage(p => p + 1)}
              className="px-3 py-1.5 bg-white border border-slate-200 rounded-lg disabled:opacity-40 hover:bg-slate-50 transition-colors"
            >Next →</button>
          </div>
        </div>
      )}
    </div>
  );
}
