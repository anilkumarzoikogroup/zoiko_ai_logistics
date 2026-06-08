import { useQuery } from "@tanstack/react-query";
import { zoikoApi } from "@/api/zoiko";
import { formatCurrency } from "@/utils/cn";
import { Truck, TrendingDown, AlertTriangle, CheckCircle2, BarChart2 } from "lucide-react";

const CARRIER_COLORS: Record<string, string> = {
  "BlueDart":    "#2563eb",
  "Delhivery":   "#7c3aed",
  "FedEx India": "#dc2626",
  "Ekart":       "#ea580c",
  "DTDC":        "#16a34a",
};

export default function CarriersPage() {
  const { data: cases = [], isLoading } = useQuery({
    queryKey: ["cases"],
    queryFn:  () => zoikoApi.listCases(),
    refetchInterval: 10000,
  });

  const { data: rates = [] } = useQuery({
    queryKey: ["contract-rates"],
    queryFn:  () => zoikoApi.listContractRates(),
  });

  // Build carrier stats from cases
  const carrierMap: Record<string, { cases: number; billed: number; overcharge: number; currency: string; states: Record<string,number> }> = {};

  for (const c of cases) {
    const name = c.carrier || "Unknown";
    if (!carrierMap[name]) carrierMap[name] = { cases: 0, billed: 0, overcharge: 0, currency: c.currency || "INR", states: {} };
    carrierMap[name].cases++;
    carrierMap[name].billed    += Number(c.amount  ?? 0);
    carrierMap[name].overcharge += Number(c.diff    ?? 0);
    carrierMap[name].states[c.state] = (carrierMap[name].states[c.state] || 0) + 1;
  }

  // Build carrier rate map
  const rateMap: Record<string, { rate_type: string; base_rate: number; currency: string }[]> = {};
  for (const r of rates) {
    const name = r.carrier;
    if (!rateMap[name]) rateMap[name] = [];
    rateMap[name].push({ rate_type: r.rate_type, base_rate: r.rate_value, currency: r.currency });
  }

  const carriers = Object.entries(carrierMap).sort((a, b) => b[1].cases - a[1].cases);

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1,2,3].map(i => <div key={i} className="h-32 bg-slate-100 rounded-xl animate-pulse" />)}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Truck className="h-6 w-6 text-slate-600" />
        <div>
          <h2 className="text-xl font-bold text-slate-800">Carrier Overview</h2>
          <p className="text-sm text-slate-500">{carriers.length} active carriers · {cases.length} total cases</p>
        </div>
      </div>

      {carriers.length === 0 && (
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-12 text-center">
          <Truck className="h-10 w-10 text-slate-300 mx-auto mb-3" />
          <p className="text-slate-500 font-medium">No carriers yet</p>
          <p className="text-slate-400 text-sm mt-1">Submit an invoice to see carrier data here</p>
        </div>
      )}

      {/* Carrier cards */}
      <div className="grid gap-4">
        {carriers.map(([name, stats]) => {
          const color  = CARRIER_COLORS[name] ?? "#64748b";
          const hasOver = stats.overcharge > 0;
          const carrierRates = rateMap[name] ?? [];
          const closedCount = stats.states["CLOSED"] || 0;
          const activeCount = stats.cases - closedCount;

          return (
            <div key={name} className="rounded-xl border border-slate-200 bg-white overflow-hidden shadow-sm">
              {/* Color bar */}
              <div style={{ height: 4, background: color }} />

              <div className="p-5">
                <div className="flex items-start justify-between gap-4">
                  {/* Left — carrier info */}
                  <div className="flex items-center gap-3 flex-1">
                    <div className="h-10 w-10 rounded-xl flex items-center justify-center" style={{ background: `${color}15`, border: `1px solid ${color}30` }}>
                      <Truck className="h-5 w-5" style={{ color }} />
                    </div>
                    <div>
                      <h3 className="font-bold text-slate-800 text-base">{name}</h3>
                      <div className="flex items-center gap-3 mt-0.5">
                        <span className="text-xs text-slate-500">{stats.cases} cases</span>
                        <span className="text-xs text-slate-300">·</span>
                        <span className="text-xs text-slate-500">{activeCount} active</span>
                        {closedCount > 0 && <>
                          <span className="text-xs text-slate-300">·</span>
                          <span className="text-xs text-emerald-600">{closedCount} closed</span>
                        </>}
                      </div>
                    </div>
                  </div>

                  {/* Right — overcharge badge */}
                  {hasOver ? (
                    <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-50 border border-red-100">
                      <AlertTriangle className="h-3.5 w-3.5 text-red-500" />
                      <span className="text-xs font-bold text-red-600">
                        {formatCurrency(stats.overcharge, stats.currency)} overcharged
                      </span>
                    </div>
                  ) : (
                    <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-50 border border-emerald-100">
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                      <span className="text-xs font-bold text-emerald-600">No overcharges</span>
                    </div>
                  )}
                </div>

                {/* Stats row */}
                <div className="grid grid-cols-3 gap-3 mt-4">
                  <div className="rounded-lg bg-slate-50 p-3">
                    <p className="text-[10px] text-slate-400 uppercase font-bold mb-1">Total Billed</p>
                    <p className="text-sm font-bold text-slate-700">{formatCurrency(stats.billed, stats.currency)}</p>
                  </div>
                  <div className="rounded-lg bg-red-50 p-3">
                    <p className="text-[10px] text-red-400 uppercase font-bold mb-1">Overcharge</p>
                    <p className="text-sm font-bold text-red-600">{formatCurrency(stats.overcharge, stats.currency)}</p>
                  </div>
                  <div className="rounded-lg bg-slate-50 p-3">
                    <p className="text-[10px] text-slate-400 uppercase font-bold mb-1">Recovery Rate</p>
                    <p className="text-sm font-bold text-slate-700">
                      {stats.billed > 0 ? `${((stats.overcharge / stats.billed) * 100).toFixed(1)}%` : "—"}
                    </p>
                  </div>
                </div>

                {/* Contract rates */}
                {carrierRates.length > 0 && (
                  <div className="mt-4 pt-4 border-t border-slate-100">
                    <p className="text-xs font-bold text-slate-500 mb-2 flex items-center gap-1.5">
                      <BarChart2 className="h-3.5 w-3.5" /> Contract Rates
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {carrierRates.map((r, i) => (
                        <span key={i} className="text-xs bg-slate-100 text-slate-600 px-2.5 py-1 rounded-full font-medium">
                          {r.rate_type}: {formatCurrency(r.base_rate, r.currency)}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {carrierRates.length === 0 && (
                  <div className="mt-3 text-xs text-amber-600 flex items-center gap-1.5">
                    <AlertTriangle className="h-3.5 w-3.5" />
                    No contract rates — go to Contracts &amp; Rates to add rates for accurate overcharge detection
                  </div>
                )}

                {/* State breakdown */}
                {Object.keys(stats.states).length > 1 && (
                  <div className="mt-3 flex items-center gap-1.5 flex-wrap">
                    {Object.entries(stats.states).map(([state, count]) => (
                      <span key={state} className="text-[10px] bg-slate-100 text-slate-500 px-2 py-0.5 rounded-full">
                        {state.replace(/_/g," ")}: {count}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Summary */}
      {carriers.length > 0 && (
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
          <div className="flex items-center gap-2 mb-3">
            <TrendingDown className="h-4 w-4 text-slate-500" />
            <p className="text-sm font-bold text-slate-700">Overall Summary</p>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <p className="text-xs text-slate-400">Total Carriers</p>
              <p className="text-xl font-bold text-slate-800">{carriers.length}</p>
            </div>
            <div>
              <p className="text-xs text-slate-400">Total Billed</p>
              <p className="text-xl font-bold text-slate-800">
                {formatCurrency(carriers.reduce((s,[,v]) => s + v.billed, 0), "INR")}
              </p>
            </div>
            <div>
              <p className="text-xs text-slate-400">Total Overcharge</p>
              <p className="text-xl font-bold text-red-600">
                {formatCurrency(carriers.reduce((s,[,v]) => s + v.overcharge, 0), "INR")}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
