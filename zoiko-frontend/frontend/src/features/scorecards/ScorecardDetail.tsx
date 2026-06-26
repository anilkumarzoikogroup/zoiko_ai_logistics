import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { scorecardApi } from "@/api/zoiko";
import type { ScorecardPeriod } from "@/types";

// ── Sub-score radar bar ───────────────────────────────────────────────────────
function SubScoreBar({ label, score, weight, color }: { label: string; score: number; weight: number; color: string }) {
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-slate-600 font-medium">{label}</span>
        <span className="text-slate-500 font-mono">{score.toFixed(1)} <span className="text-slate-400">× {weight}</span></span>
      </div>
      <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${score}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}

// ── Large circular gauge ──────────────────────────────────────────────────────
function BigGauge({ score, threshold }: { score: number; threshold: number }) {
  const r = 52;
  const cx = 64;
  const cy = 64;
  const circ = 2 * Math.PI * r;
  const dash = (score / 100) * circ;
  const color = score >= threshold ? "#10b981" : score >= threshold - 10 ? "#f59e0b" : "#ef4444";
  const label = score >= threshold ? "Good" : score >= threshold - 10 ? "At Risk" : "Breach";
  return (
    <div className="flex flex-col items-center gap-1">
      <svg width={128} height={128} viewBox="0 0 128 128">
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="#f1f5f9" strokeWidth={12} />
        <circle
          cx={cx} cy={cy} r={r}
          fill="none"
          stroke={color}
          strokeWidth={12}
          strokeDasharray={`${dash} ${circ - dash}`}
          strokeLinecap="round"
          transform={`rotate(-90 ${cx} ${cy})`}
        />
        <text x={cx} y={cy - 4} textAnchor="middle" fontSize={26} fontWeight="800" fill={color} fontFamily="monospace">
          {score.toFixed(0)}
        </text>
        <text x={cx} y={cy + 16} textAnchor="middle" fontSize={11} fill="#94a3b8">
          / 100
        </text>
      </svg>
      <span className="text-xs font-semibold px-2 py-0.5 rounded-full" style={{ backgroundColor: `${color}20`, color }}>
        {label}
      </span>
    </div>
  );
}

// ── Claim status badge ────────────────────────────────────────────────────────
const STATUS_COLORS: Record<string, string> = {
  OPEN:      "bg-blue-50 text-blue-700",
  RESOLVED:  "bg-emerald-50 text-emerald-700",
  REJECTED:  "bg-red-50 text-red-700",
  PENDING:   "bg-amber-50 text-amber-700",
};

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_COLORS[status] ?? "bg-slate-100 text-slate-600"}`}>
      {status}
    </span>
  );
}

function formatDate(iso: string | null | undefined) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

function formatPeriod(start: string, end: string) {
  return `${formatDate(start)} – ${formatDate(end)}`;
}

const SUB_COLORS = {
  on_time:    "#10b981",
  quality:    "#6366f1",
  frequency:  "#f59e0b",
  resolution: "#3b82f6",
};

export default function ScorecardDetail() {
  const { id } = useParams<{ id: string }>();

  const { data: sc, isLoading, error } = useQuery<ScorecardPeriod>({
    queryKey: ["scorecard", id],
    queryFn:  () => scorecardApi.getScorecard(id!),
    enabled:  !!id,
  });

  if (isLoading) {
    return (
      <div className="flex justify-center py-20">
        <div className="h-8 w-8 rounded-full border-2 border-blue-600 border-t-transparent animate-spin" />
      </div>
    );
  }

  if (error || !sc) {
    return (
      <div className="p-6 max-w-3xl mx-auto">
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          Failed to load scorecard. {error instanceof Error ? error.message : ""}
        </div>
      </div>
    );
  }

  const subScores = sc.sub_scores;
  const raw = sc.raw_metrics;

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm text-slate-500">
        <Link to="/scorecards" className="hover:text-blue-600">Scorecards</Link>
        <span>/</span>
        <span className="text-slate-900 font-medium">{sc.carrier_id}</span>
      </div>

      {/* Hero card */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
        <div className="flex flex-col sm:flex-row gap-6 items-start">
          <BigGauge score={sc.composite_score} threshold={sc.contracted_threshold} />

          <div className="flex-1 space-y-3">
            <div>
              <h1 className="text-xl font-bold text-slate-900">{sc.carrier_id}</h1>
              <p className="text-sm text-slate-500">{formatPeriod(sc.period_start, sc.period_end)}</p>
            </div>

            {/* KPI row */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                { label: "On-Time Rate",  val: `${(sc.on_time_rate * 100).toFixed(0)}%` },
                { label: "Claim Quality", val: `${((1 - sc.damage_rate) * 100).toFixed(0)}%` },
                { label: "Total Claims",  val: sc.claim_frequency.toFixed(0) },
                { label: "Avg Turnaround",val: `${sc.dispute_turnaround_days.toFixed(0)}d` },
              ].map(k => (
                <div key={k.label} className="rounded-lg bg-slate-50 px-3 py-2">
                  <div className="text-xs text-slate-500">{k.label}</div>
                  <div className="text-lg font-bold text-slate-900 font-mono">{k.val}</div>
                </div>
              ))}
            </div>

            {/* Breach alert */}
            {sc.breach_detected && (
              <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-2.5 flex items-center gap-2">
                <span className="text-red-500 text-base">⚠</span>
                <div>
                  <p className="text-sm font-semibold text-red-700">Performance Breach</p>
                  <p className="text-xs text-red-600">
                    Score {sc.composite_score.toFixed(1)} below threshold {sc.contracted_threshold} ·
                    ₹{sc.breach_amount.toLocaleString("en-IN")} unrecovered exposure
                  </p>
                </div>
              </div>
            )}

            {/* Threshold line */}
            <p className="text-xs text-slate-400">
              Contracted threshold: <span className="font-mono font-semibold text-slate-600">{sc.contracted_threshold}/100</span>
            </p>
          </div>
        </div>
      </div>

      {/* Sub-score breakdown */}
      {subScores && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
          <h2 className="text-sm font-semibold text-slate-700 mb-4">Score Breakdown</h2>
          <div className="space-y-4">
            {(["on_time", "quality", "frequency", "resolution"] as const).map(key => {
              const s = subScores[key];
              return (
                <SubScoreBar
                  key={key}
                  label={`${s.label} (${(s.weight * 100).toFixed(0)}%)`}
                  score={s.score}
                  weight={s.weight}
                  color={SUB_COLORS[key]}
                />
              );
            })}
          </div>

          <div className="mt-5 pt-4 border-t border-slate-100">
            <div className="flex justify-between text-sm font-semibold text-slate-700">
              <span>Composite Score</span>
              <span className="font-mono text-lg">{sc.composite_score.toFixed(2)}</span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5 font-mono">
              0.40×{(sc.on_time_rate * 100).toFixed(1)} + 0.30×{((1 - sc.damage_rate) * 100).toFixed(1)} + 0.20×{subScores.frequency.score.toFixed(1)} + 0.10×{subScores.resolution.score.toFixed(1)}
            </p>
          </div>
        </div>
      )}

      {/* Raw metrics */}
      {raw && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
          <h2 className="text-sm font-semibold text-slate-700 mb-4">Underlying Data</h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
            {[
              { label: "Total Claims",     val: raw.total_claims },
              { label: "Total Claimed",    val: `₹${raw.total_claimed.toLocaleString("en-IN", { maximumFractionDigits: 0 })}` },
              { label: "Total Approved",   val: `₹${raw.total_approved.toLocaleString("en-IN", { maximumFractionDigits: 0 })}` },
              { label: "Avg Turnaround",   val: `${raw.avg_turnaround_days.toFixed(1)} days` },
              { label: "SLA Cases",        val: raw.sla_cases },
              { label: "On-Time Cases",    val: raw.on_time_cases },
            ].map(m => (
              <div key={m.label} className="rounded-lg bg-slate-50 px-3 py-2">
                <div className="text-xs text-slate-500">{m.label}</div>
                <div className="text-base font-bold text-slate-900 font-mono">{m.val}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent claims table */}
      {sc.recent_claims && sc.recent_claims.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
          <h2 className="text-sm font-semibold text-slate-700 mb-4">Recent Claims in Period</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs font-medium text-slate-500 border-b border-slate-100">
                  <th className="pb-2 pr-4">Reference</th>
                  <th className="pb-2 pr-4">Type</th>
                  <th className="pb-2 pr-4 text-right">Claimed</th>
                  <th className="pb-2 pr-4 text-right">Approved</th>
                  <th className="pb-2 pr-4">Filed</th>
                  <th className="pb-2">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {sc.recent_claims.map(c => (
                  <tr key={c.id} className="hover:bg-slate-50">
                    <td className="py-2 pr-4 font-mono text-xs text-slate-700">{c.claim_reference || c.id.slice(0, 8)}</td>
                    <td className="py-2 pr-4 text-slate-600">{c.claim_type}</td>
                    <td className="py-2 pr-4 text-right font-mono">₹{c.claimed_amount.toLocaleString("en-IN")}</td>
                    <td className="py-2 pr-4 text-right font-mono">
                      {c.approved_amount != null ? `₹${c.approved_amount.toLocaleString("en-IN")}` : "—"}
                    </td>
                    <td className="py-2 pr-4 text-slate-500 text-xs">{formatDate(c.filed_at)}</td>
                    <td className="py-2"><StatusBadge status={c.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-3">
        <Link to="/scorecards" className="px-4 py-2 text-sm text-slate-600 border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors">
          ← Back to list
        </Link>
        <Link to="/scorecards/new" className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors">
          + New Scorecard
        </Link>
      </div>
    </div>
  );
}
