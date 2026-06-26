import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { scorecardApi } from "@/api/zoiko";
import type { ScorecardPeriod } from "@/types";

// Circular gauge SVG — single arc showing 0-100 score
function ScoreGauge({ score, threshold }: { score: number; threshold: number }) {
  const r = 28;
  const cx = 36;
  const cy = 36;
  const circ = 2 * Math.PI * r;
  const dash = (score / 100) * circ;
  const color = score >= threshold ? "#10b981" : score >= threshold - 10 ? "#f59e0b" : "#ef4444";
  return (
    <svg width={72} height={72} viewBox="0 0 72 72">
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="#e2e8f0" strokeWidth={7} />
      <circle
        cx={cx} cy={cy} r={r}
        fill="none"
        stroke={color}
        strokeWidth={7}
        strokeDasharray={`${dash} ${circ - dash}`}
        strokeLinecap="round"
        transform={`rotate(-90 ${cx} ${cy})`}
      />
      <text x={cx} y={cy + 5} textAnchor="middle" fontSize={14} fontWeight="700" fill={color} fontFamily="monospace">
        {score.toFixed(0)}
      </text>
    </svg>
  );
}

// Trend arrow chip
function TrendArrow({ score, threshold }: { score: number; threshold: number }) {
  const gap = score - threshold;
  if (gap >= 5)  return <span className="text-xs font-semibold text-emerald-600">▲ {gap.toFixed(1)}</span>;
  if (gap >= 0)  return <span className="text-xs font-semibold text-amber-500">► {gap.toFixed(1)}</span>;
  return <span className="text-xs font-semibold text-red-500">▼ {Math.abs(gap).toFixed(1)}</span>;
}

// Four metric chips
function MetricChips({ sc }: { sc: ScorecardPeriod }) {
  const chips = [
    { label: "On-Time",   val: `${(sc.on_time_rate * 100).toFixed(0)}%`, ok: sc.on_time_rate >= 0.9 },
    { label: "Quality",   val: `${((1 - sc.damage_rate) * 100).toFixed(0)}%`, ok: sc.damage_rate < 0.1 },
    { label: "Claims",    val: sc.claim_frequency.toFixed(0), ok: sc.claim_frequency < 3 },
    { label: "Turnaround",val: `${sc.dispute_turnaround_days.toFixed(0)}d`, ok: sc.dispute_turnaround_days < 30 },
  ];
  return (
    <div className="flex gap-1.5 flex-wrap mt-2">
      {chips.map(c => (
        <span key={c.label} className={`px-2 py-0.5 rounded text-xs font-medium ${c.ok ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>
          {c.label}: {c.val}
        </span>
      ))}
    </div>
  );
}

function formatPeriod(start: string, end: string) {
  const s = new Date(start).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
  const e = new Date(end).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
  return `${s} – ${e}`;
}

export default function ScorecardList() {
  const [filterCarrier, setFilterCarrier] = useState("");

  const { data: carriers = [] } = useQuery({
    queryKey: ["scorecard-carriers"],
    queryFn: () => scorecardApi.listCarriers(),
  });

  const { data: scorecards = [], isLoading, error } = useQuery({
    queryKey: ["scorecards", filterCarrier],
    queryFn: () => scorecardApi.listScorecards(filterCarrier || undefined),
  });

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Supplier Scorecards</h1>
          <p className="text-sm text-slate-500 mt-0.5">Auto-computed carrier performance — claims + SLA data</p>
        </div>
        <Link
          to="/scorecards/new"
          className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors"
        >
          + Compute Scorecard
        </Link>
      </div>

      {/* Filter */}
      <div className="mb-5">
        <select
          value={filterCarrier}
          onChange={e => setFilterCarrier(e.target.value)}
          className="w-48 px-3 py-2 text-sm border border-slate-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">All carriers</option>
          {carriers.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>

      {/* States */}
      {isLoading && (
        <div className="flex justify-center py-16">
          <div className="h-8 w-8 rounded-full border-2 border-blue-600 border-t-transparent animate-spin" />
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          Failed to load scorecards. Check that the SC-004 scorecard gateway is running on port 8030.
        </div>
      )}

      {!isLoading && !error && scorecards.length === 0 && (
        <div className="text-center py-16 text-slate-500">
          <div className="text-4xl mb-3">⭐</div>
          <p className="font-medium">No scorecards yet</p>
          <p className="text-sm mt-1">Use <Link to="/scorecards/new" className="text-blue-600 underline">Compute Scorecard</Link> to generate one for a carrier.</p>
        </div>
      )}

      {/* Cards grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {scorecards.map((sc: ScorecardPeriod) => (
          <Link
            key={sc.id}
            to={`/scorecards/${sc.id}`}
            className="group block rounded-xl border border-slate-200 bg-white p-4 shadow-sm hover:shadow-md hover:border-blue-300 transition-all"
          >
            {/* Top row */}
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <div className="font-semibold text-slate-900 truncate">{sc.carrier_id}</div>
                <div className="text-xs text-slate-400 mt-0.5">{formatPeriod(sc.period_start, sc.period_end)}</div>
              </div>
              <ScoreGauge score={sc.composite_score} threshold={sc.contracted_threshold} />
            </div>

            {/* Trend vs threshold */}
            <div className="flex items-center gap-2 mt-1">
              <span className="text-xs text-slate-500">vs {sc.contracted_threshold} threshold</span>
              <TrendArrow score={sc.composite_score} threshold={sc.contracted_threshold} />
            </div>

            {/* Breach badge */}
            {sc.breach_detected && (
              <div className="mt-2 inline-flex items-center gap-1 px-2 py-0.5 rounded bg-red-50 border border-red-200 text-red-700 text-xs font-medium">
                ⚠ Breach — ₹{sc.breach_amount.toLocaleString("en-IN")} exposure
              </div>
            )}

            <MetricChips sc={sc} />
          </Link>
        ))}
      </div>
    </div>
  );
}
