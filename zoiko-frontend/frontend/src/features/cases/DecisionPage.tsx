import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { zoikoApi } from "@/api/zoiko";
import { formatCurrency, formatDate, cn } from "@/utils/cn";
import { Search, ArrowUpDown, TrendingUp, TrendingDown } from "lucide-react";
import { useState } from "react";
import type { Case } from "@/types";

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

function CaseCard({ c }: { c: Case }) {
  const nav = useNavigate();
  const isOvercharge = c.diff > 0;

  return (
    <div
      onClick={() => nav(`/cases/${c.id}`)}
      className="bg-white rounded-xl border border-slate-200 shadow-sm p-4 hover:shadow-md hover:-translate-y-0.5 transition-all duration-150 cursor-pointer group"
    >
      <div className="flex items-start justify-between mb-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-[13px] font-semibold text-slate-800 truncate">{c.carrier || "—"}</span>
            {isOvercharge
              ? <TrendingUp className="h-3.5 w-3.5 text-red-500 flex-shrink-0" />
              : <TrendingDown className="h-3.5 w-3.5 text-amber-500 flex-shrink-0" />
            }
          </div>
          <p className="text-[11px] text-slate-400 truncate mt-0.5">{c.shipment_ref || "—"}</p>
        </div>
        <StateBadge state={c.state} />
      </div>

      <div className="flex items-end justify-between mt-3">
        <div>
          <p className="text-[10px] text-slate-400 font-medium">Amount</p>
          <p className="text-sm font-bold text-slate-800">{formatCurrency(c.amount, c.currency)}</p>
        </div>
        <div className="text-right">
          <p className="text-[10px] text-slate-400 font-medium">{isOvercharge ? "Overcharge" : "Undercharge"}</p>
          <p className={cn(
            "text-sm font-bold",
            isOvercharge ? "text-red-600" : "text-amber-600"
          )}>
            {isOvercharge ? "+" : ""}{formatCurrency(Math.abs(c.diff), c.currency)}
          </p>
        </div>
      </div>

      <div className="flex items-center justify-between mt-3 pt-3 border-t border-slate-100">
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-slate-400">Confidence</span>
          <ConfidenceBadge value={c.confidence ?? null} />
        </div>
        <div className="flex items-center gap-2">
          <code className="text-[10px] text-slate-300 font-mono">{c.id.slice(0, 8)}</code>
          <span className="text-[10px] text-slate-400">{formatDate(c.opened_at)}</span>
        </div>
      </div>
    </div>
  );
}

function CardSkeleton() {
  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4 animate-pulse">
      <div className="flex items-start justify-between mb-3">
        <div className="space-y-2 flex-1">
          <div className="h-3 w-28 bg-slate-100 rounded-full" />
          <div className="h-2.5 w-20 bg-slate-100 rounded-full" />
        </div>
        <div className="h-5 w-20 bg-slate-100 rounded-full" />
      </div>
      <div className="flex items-end justify-between mb-3">
        <div className="space-y-1.5">
          <div className="h-2 w-12 bg-slate-100 rounded-full" />
          <div className="h-4 w-16 bg-slate-100 rounded-full" />
        </div>
        <div className="space-y-1.5 text-right">
          <div className="h-2 w-16 bg-slate-100 rounded-full ml-auto" />
          <div className="h-4 w-20 bg-slate-100 rounded-full ml-auto" />
        </div>
      </div>
      <div className="flex items-center justify-between pt-3 border-t border-slate-100">
        <div className="h-2.5 w-24 bg-slate-100 rounded-full" />
        <div className="h-2.5 w-28 bg-slate-100 rounded-full" />
      </div>
    </div>
  );
}

export default function DecisionPage() {
  const nav = useNavigate();
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState<"diff" | "amount" | "confidence" | "date">("diff");

  const { data: paged, isLoading } = useQuery({
    queryKey: ["decision-cases"],
    queryFn:  () => zoikoApi.listCasesPaged({ page: 1, page_size: 200 }),
    refetchInterval: 10000,
  });

  const allCases = paged?.cases ?? [];

  const overcharges = allCases
    .filter(c => c.diff > 0)
    .filter(c => !search || c.carrier?.toLowerCase().includes(search.toLowerCase()) || c.shipment_ref?.toLowerCase().includes(search.toLowerCase()) || c.id.includes(search));

  const undercharges = allCases
    .filter(c => c.diff < 0)
    .filter(c => !search || c.carrier?.toLowerCase().includes(search.toLowerCase()) || c.shipment_ref?.toLowerCase().includes(search.toLowerCase()) || c.id.includes(search));

  const sortCases = (list: Case[]) => {
    switch (sortBy) {
      case "diff":       return [...list].sort((a, b) => Math.abs(b.diff) - Math.abs(a.diff));
      case "amount":     return [...list].sort((a, b) => b.amount - a.amount);
      case "confidence": return [...list].sort((a, b) => (b.confidence ?? 0) - (a.confidence ?? 0));
      case "date":       return [...list].sort((a, b) => new Date(b.opened_at).getTime() - new Date(a.opened_at).getTime());
      default:           return list;
    }
  };

  const sortedOver = sortCases(overcharges);
  const sortedUnder = sortCases(undercharges);

  const totalOver = allCases.filter(c => c.diff > 0).length;
  const totalUnder = allCases.filter(c => c.diff < 0).length;

  return (
    <div className="space-y-5">

      {/* ── Header ────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Decision Dashboard</h1>
          <p className="text-sm text-slate-400 mt-0.5">
            {totalOver} overcharges · {totalUnder} undercharges · {(allCases.length || 0)} total cases
          </p>
        </div>
      </div>

      {/* ── Summary bar ──────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-white rounded-xl border border-slate-200 border-l-4 border-l-red-400 px-4 py-3 shadow-sm">
          <p className="text-[10px] text-slate-500 font-semibold uppercase tracking-wide">Overcharges</p>
          <p className="text-2xl font-bold text-red-600 mt-1">{totalOver}</p>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 border-l-4 border-l-amber-400 px-4 py-3 shadow-sm">
          <p className="text-[10px] text-slate-500 font-semibold uppercase tracking-wide">Undercharges</p>
          <p className="text-2xl font-bold text-amber-600 mt-1">{totalUnder}</p>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 border-l-4 border-l-blue-400 px-4 py-3 shadow-sm">
          <p className="text-[10px] text-slate-500 font-semibold uppercase tracking-wide">Pending Approval</p>
          <p className="text-2xl font-bold text-blue-600 mt-1">
            {allCases.filter(c => c.state === "APPROVAL_PENDING").length}
          </p>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 border-l-4 border-l-emerald-400 px-4 py-3 shadow-sm">
          <p className="text-[10px] text-slate-500 font-semibold uppercase tracking-wide">Ready to Execute</p>
          <p className="text-2xl font-bold text-emerald-600 mt-1">
            {allCases.filter(c => c.state === "EXECUTION_READY").length}
          </p>
        </div>
      </div>

      {/* ── Toolbar ───────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 bg-white rounded-xl border border-slate-200 shadow-sm px-4 py-3">
        <div className="relative flex-1 max-w-xs">
          <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            className="pl-9 pr-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/30 w-full"
            placeholder="Search carrier, shipment, ID…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        <div className="flex items-center gap-1.5">
          <ArrowUpDown className="h-3.5 w-3.5 text-slate-400" />
          <select
            value={sortBy}
            onChange={e => setSortBy(e.target.value as typeof sortBy)}
            className="text-xs border border-slate-200 rounded-lg px-2 py-1.5 bg-white text-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
          >
            <option value="diff">Sort by Diff</option>
            <option value="amount">Sort by Amount</option>
            <option value="confidence">Sort by Confidence</option>
            <option value="date">Sort by Date</option>
          </select>
        </div>
      </div>

      {/* ── Two columns ───────────────────────────────────────────── */}
      {isLoading ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <div className="space-y-3">
            {[0,1,2,3].map(i => <CardSkeleton key={i} />)}
          </div>
          <div className="space-y-3">
            {[0,1,2].map(i => <CardSkeleton key={i} />)}
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">

          {/* ── Overcharges Column ─────────────────────────────── */}
          <div className="space-y-3">
            <div className="flex items-center gap-2 px-0.5">
              <TrendingUp className="h-4 w-4 text-red-500" />
              <h2 className="text-sm font-bold text-slate-700">
                Overcharges
                <span className="ml-1.5 text-slate-400 font-medium">({sortedOver.length})</span>
              </h2>
            </div>
            {sortedOver.length === 0 ? (
              <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-8 text-center">
                <div className="h-10 w-10 rounded-full bg-slate-100 flex items-center justify-center mx-auto mb-3">
                  <TrendingUp className="h-5 w-5 text-slate-300" />
                </div>
                <p className="font-semibold text-slate-600 text-sm">No overcharges found</p>
                <p className="text-xs text-slate-400 mt-1">
                  {search ? "Try a different search term" : "All invoices match contract rates"}
                </p>
              </div>
            ) : (
              sortedOver.map(c => <CaseCard key={c.id} c={c} />)
            )}
          </div>

          {/* ── Undercharges Column ────────────────────────────── */}
          <div className="space-y-3">
            <div className="flex items-center gap-2 px-0.5">
              <TrendingDown className="h-4 w-4 text-amber-500" />
              <h2 className="text-sm font-bold text-slate-700">
                Undercharges
                <span className="ml-1.5 text-slate-400 font-medium">({sortedUnder.length})</span>
              </h2>
            </div>
            {sortedUnder.length === 0 ? (
              <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-8 text-center">
                <div className="h-10 w-10 rounded-full bg-slate-100 flex items-center justify-center mx-auto mb-3">
                  <TrendingDown className="h-5 w-5 text-slate-300" />
                </div>
                <p className="font-semibold text-slate-600 text-sm">No undercharges found</p>
                <p className="text-xs text-slate-400 mt-1">
                  {search ? "Try a different search term" : "All invoices meet the minimum contract rate"}
                </p>
              </div>
            ) : (
              sortedUnder.map(c => <CaseCard key={c.id} c={c} />)
            )}
          </div>

        </div>
      )}

      {/* ── Footer ────────────────────────────────────────────────── */}
      {allCases.length > 0 && (
        <p className="text-[10px] text-slate-400 text-center pt-2">
          Showing {sortedOver.length + sortedUnder.length} of {allCases.length} loaded cases ·
          Click any card to view details · Auto-refreshes every 10s
        </p>
      )}
    </div>
  );
}
