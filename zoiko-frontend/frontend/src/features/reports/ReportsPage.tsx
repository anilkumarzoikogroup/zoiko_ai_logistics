import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { BarChart2, TrendingUp, ShieldCheck, AlertCircle, FileText } from "lucide-react";

interface RecoveryReport {
  by_carrier: { carrier_id: string; case_count: number; total_recovered: number; total_overcharge: number }[];
  monthly: { month: string; cases_opened: number; cases_closed: number; recovered: number }[];
}

interface ComplianceReport {
  total_cases: number;
  closed_cases: number;
  closure_rate: number;
  tokens_issued: number;
  tokens_consumed: number;
  token_utilisation: number;
  acr_count: number;
  worm_entries: number;
  override_count: number;
  sod_notes: string;
}

const fmt = (n: number, currency = "INR") =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency, maximumFractionDigits: 0 }).format(n);

export default function ReportsPage() {
  const { data: recovery, isLoading: rLoading } = useQuery<RecoveryReport>({
    queryKey: ["reports-recovery"],
    queryFn: async () => { const { data } = await api.get("/v1/reports/recovery"); return data; },
    staleTime: 60_000,
  });

  const { data: compliance, isLoading: cLoading } = useQuery<ComplianceReport>({
    queryKey: ["reports-compliance"],
    queryFn: async () => { const { data } = await api.get("/v1/reports/compliance"); return data; },
    staleTime: 60_000,
  });

  const isLoading = rLoading || cLoading;

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center gap-3">
        <BarChart2 className="h-6 w-6 text-slate-600" />
        <div>
          <h1 className="text-xl font-semibold text-slate-800">Reports</h1>
          <p className="text-sm text-slate-500">Recovery performance and compliance summary</p>
        </div>
      </div>

      {isLoading && (
        <div className="grid grid-cols-4 gap-4">
          {[1,2,3,4].map(i => <div key={i} className="h-24 bg-slate-100 rounded-xl animate-pulse" />)}
        </div>
      )}

      {/* Compliance KPIs */}
      {compliance && (
        <section>
          <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3 flex items-center gap-2">
            <ShieldCheck className="h-4 w-4" /> Compliance Overview
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { label: "Total Cases",        value: compliance.total_cases,                   sub: `${compliance.closed_cases} closed` },
              { label: "Closure Rate",       value: `${(compliance.closure_rate * 100).toFixed(1)}%`, sub: "cases resolved" },
              { label: "Token Utilisation",  value: `${(compliance.token_utilisation * 100).toFixed(1)}%`, sub: `${compliance.tokens_issued} issued` },
              { label: "WORM Entries",       value: compliance.worm_entries,                  sub: `${compliance.acr_count} ACRs` },
            ].map(kpi => (
              <div key={kpi.label} className="bg-white border border-slate-200 rounded-xl p-4">
                <p className="text-xs text-slate-500">{kpi.label}</p>
                <p className="text-2xl font-bold text-slate-800 mt-1">{kpi.value}</p>
                <p className="text-xs text-slate-400 mt-0.5">{kpi.sub}</p>
              </div>
            ))}
          </div>
          {compliance.override_count > 0 && (
            <div className="mt-3 flex items-center gap-2 text-sm text-orange-600 bg-orange-50 rounded-lg px-4 py-2">
              <AlertCircle className="h-4 w-4 flex-shrink-0" />
              <span>{compliance.override_count} governance override(s) recorded this period — review in Policy &gt; Overrides.</span>
            </div>
          )}
          <p className="mt-2 text-xs text-slate-400">{compliance.sod_notes}</p>
        </section>
      )}

      {/* Recovery by Carrier */}
      {recovery && recovery.by_carrier.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3 flex items-center gap-2">
            <TrendingUp className="h-4 w-4" /> Recovery by Carrier
          </h2>
          <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 border-b border-slate-200">
                <tr>
                  {["Carrier","Cases","Total Overcharge","Total Recovered","Recovery Rate"].map(h => (
                    <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {recovery.by_carrier.map((row, i) => {
                  const rate = row.total_overcharge > 0 ? row.total_recovered / row.total_overcharge : 0;
                  return (
                    <tr key={i} className="hover:bg-slate-50 transition">
                      <td className="px-4 py-3 font-medium text-slate-800">{row.carrier_id || "—"}</td>
                      <td className="px-4 py-3 text-slate-600">{row.case_count}</td>
                      <td className="px-4 py-3 text-red-600">{fmt(row.total_overcharge)}</td>
                      <td className="px-4 py-3 text-green-600 font-medium">{fmt(row.total_recovered)}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
                            <div className="h-full bg-green-500 rounded-full" style={{ width: `${Math.min(rate * 100, 100)}%` }} />
                          </div>
                          <span className="text-xs text-slate-500 w-10 text-right">{(rate * 100).toFixed(0)}%</span>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Monthly trend */}
      {recovery && recovery.monthly.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3 flex items-center gap-2">
            <FileText className="h-4 w-4" /> Monthly Case Trend
          </h2>
          <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 border-b border-slate-200">
                <tr>
                  {["Month","Opened","Closed","Recovered"].map(h => (
                    <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {recovery.monthly.map((row, i) => (
                  <tr key={i} className="hover:bg-slate-50 transition">
                    <td className="px-4 py-3 text-slate-600">{row.month}</td>
                    <td className="px-4 py-3 text-slate-600">{row.cases_opened}</td>
                    <td className="px-4 py-3 text-slate-600">{row.cases_closed}</td>
                    <td className="px-4 py-3 text-green-600 font-medium">{fmt(row.recovered)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {!isLoading && !recovery?.by_carrier.length && (
        <div className="text-center py-16 text-slate-400">
          <BarChart2 className="h-10 w-10 mx-auto mb-3 opacity-30" />
          <p className="font-medium">No report data yet</p>
          <p className="text-sm mt-1">Reports populate as cases are closed and recoveries are settled.</p>
        </div>
      )}
    </div>
  );
}
