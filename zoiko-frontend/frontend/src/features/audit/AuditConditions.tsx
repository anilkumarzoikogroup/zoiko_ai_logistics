import { useQuery } from "@tanstack/react-query";
import { zoikoApi } from "@/api/zoiko";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { cn } from "@/utils/cn";
import type { Case } from "@/types";

const COLORS = ["#1d4ed8","#ea580c","#7c3aed","#dc2626","#16a34a","#0891b2","#e879f9","#f97316"];

function cellBg(v: number) {
  if (v >= 60) return "bg-emerald-50 text-emerald-800";
  if (v >= 40) return "bg-yellow-50 text-yellow-800";
  if (v >= 15) return "bg-orange-50 text-orange-800";
  if (v >= 8)  return "bg-red-50 text-red-700";
  return "bg-red-100 text-red-800";
}

function computeCarrierStats(cases: Case[]) {
  const map: Record<string, { total: number; overcharged: number; amount: number; diff: number }> = {};
  for (const c of cases) {
    const carrier = c.carrier || "Unknown";
    if (!map[carrier]) map[carrier] = { total: 0, overcharged: 0, amount: 0, diff: 0 };
    map[carrier].total += 1;
    map[carrier].amount += c.amount ?? 0;
    if ((c.diff ?? 0) > 0) {
      map[carrier].overcharged += 1;
      map[carrier].diff += c.diff ?? 0;
    }
  }
  return Object.entries(map)
    .sort((a, b) => b[1].diff - a[1].diff)
    .map(([carrier, v]) => ({
      carrier,
      total: v.total,
      overcharged: v.overcharged,
      correct: v.total - v.overcharged,
      overchargeRate: parseFloat(((v.overcharged / (v.total || 1)) * 100).toFixed(1)),
      correctRate: parseFloat((((v.total - v.overcharged) / (v.total || 1)) * 100).toFixed(1)),
      amount: v.amount,
      diff: v.diff,
      diffLakhs: parseFloat((v.diff / 100000).toFixed(2)),
    }));
}

const CONDITIONS = [
  "Rated Equal Billed",
  "Over Billed",
  "Valid (No Dispute)",
  "Duplicate",
  "Missing POD",
  "Rate Mismatch",
  "Accessorial",
  "Tax",
];

export default function AuditConditions() {
  const { data: cases = [] } = useQuery({ queryKey: ["cases"], queryFn: () => zoikoApi.listCases() });

  const caseList = cases as Case[];
  const carrierStats = computeCarrierStats(caseList);

  const bestCarrier   = carrierStats.reduce((b, c) => c.correctRate > (b?.correctRate ?? 0) ? c : b, null as typeof carrierStats[0] | null);
  const worstCarrier  = carrierStats.reduce((b, c) => c.overchargeRate > (b?.overchargeRate ?? 0) ? c : b, null as typeof carrierStats[0] | null);
  const totalDiff     = caseList.reduce((s, c) => s + (c.diff ?? 0), 0);

  return (
    <div className="space-y-6">

      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-zoiko-navy">Audit Conditions</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Invoice audit result breakdown by carrier · live data
        </p>
      </div>

      {/* SC-001 Ruleset */}
      <div className="rounded-xl border border-blue-200 bg-blue-50 p-5">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-xs font-bold bg-blue-600 text-white px-2.5 py-0.5 rounded-full">SC-001</span>
          <h2 className="text-sm font-bold text-blue-900">Active Ruleset — Freight Overcharge Detection</h2>
          <span className="ml-auto text-xs font-semibold text-emerald-600 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">ACTIVE</span>
        </div>
        <div className="grid grid-cols-2 gap-3">
          {[
            { rule: "FUEL_CHARGE",   confidence: "100%", weight: "50%", desc: "Exact contract fuel rate match — disallowed surcharges flagged" },
            { rule: "ACCESSORIAL",   confidence: "92%",  weight: "50%", desc: "Unauthorized accessorial charges not in contract" },
          ].map(r => (
            <div key={r.rule} className="bg-white rounded-lg p-3 border border-blue-100">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-bold text-slate-700">{r.rule}</span>
                <div className="flex gap-2">
                  <span className="text-[10px] bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded font-bold">Confidence {r.confidence}</span>
                  <span className="text-[10px] bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded font-bold">Weight {r.weight}</span>
                </div>
              </div>
              <p className="text-xs text-slate-500">{r.desc}</p>
            </div>
          ))}
        </div>
        <p className="text-xs text-blue-600 mt-3 font-medium">
          Combined AI Confidence: <strong>96%</strong> (= 50% × 100% + 50% × 92%) — deterministic, never changes
        </p>
      </div>

      {caseList.length === 0 ? (
        <Card>
          <CardContent className="flex items-center justify-center py-16 text-sm text-muted-foreground">
            No case data yet — create cases to see audit condition analysis.
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Legend */}
          <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
            {[
              { cls: "bg-emerald-100", label: "≥ 60% — Rated Equal Billed (Good)" },
              { cls: "bg-yellow-100",  label: "40–60% — Monitor" },
              { cls: "bg-orange-100",  label: "15–40% — Investigate" },
              { cls: "bg-red-100",     label: "< 15% — Action Required" },
            ].map(({ cls, label }) => (
              <span key={label} className="flex items-center gap-1.5">
                <span className={cn("h-3 w-3 rounded", cls)} />
                {label}
              </span>
            ))}
          </div>

          {/* Carrier breakdown table */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Carrier Audit Breakdown</CardTitle>
            </CardHeader>
            <CardContent className="p-0 overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr>
                    <th className="bg-zoiko-navy text-white text-left text-[11px] font-semibold px-4 py-3 min-w-[110px]">
                      Carrier
                    </th>
                    <th className="bg-zoiko-navy text-white text-[11px] font-semibold px-3 py-3 text-center">Total Cases</th>
                    <th className="bg-zoiko-navy text-white text-[11px] font-semibold px-3 py-3 text-center">Correct Rate</th>
                    <th className="bg-zoiko-navy text-white text-[11px] font-semibold px-3 py-3 text-center">Overcharged</th>
                    <th className="bg-zoiko-navy text-white text-[11px] font-semibold px-3 py-3 text-center">Overcharge Rate</th>
                    <th className="bg-zoiko-navy text-white text-[11px] font-semibold px-3 py-3 text-right">Total Diff</th>
                  </tr>
                </thead>
                <tbody>
                  {carrierStats.map((cs, i) => (
                    <tr key={cs.carrier} className={i % 2 === 0 ? "" : "bg-gray-50/50"}>
                      <td className="px-4 py-3 font-semibold text-zoiko-navy border-b text-sm whitespace-nowrap">
                        {cs.carrier}
                      </td>
                      <td className="px-3 py-3 text-center font-bold text-sm border-b">{cs.total}</td>
                      <td className={cn("px-3 py-3 text-center font-bold text-sm border-b", cellBg(cs.correctRate))}>
                        {cs.correctRate}%
                      </td>
                      <td className="px-3 py-3 text-center text-sm border-b text-amber-700 font-semibold">{cs.overcharged}</td>
                      <td className={cn("px-3 py-3 text-center font-bold text-sm border-b", cellBg(100 - cs.overchargeRate))}>
                        {cs.overchargeRate}%
                      </td>
                      <td className="px-4 py-3 text-right font-bold text-sm border-b text-red-700">
                        {cs.diff > 0 ? `$${cs.diffLakhs}L` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>

          {/* Overcharge volume bar chart */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Overcharge Volume by Carrier</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart
                  data={carrierStats.filter(c => c.diff > 0)}
                  margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="carrier" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 10 }} width={55}
                    tickFormatter={(v: number) => v >= 100000 ? `$${(v/100000).toFixed(1)}L` : `$${(v/1000).toFixed(0)}k`} />
                  <Tooltip formatter={(v: number) => [`$${v.toLocaleString()}`, "Overcharge"]} />
                  <Bar dataKey="diff" radius={[4,4,0,0]}>
                    {carrierStats.filter(c => c.diff > 0).map((_, i) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Summary cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              {
                label: "Most Overcharged",
                value: worstCarrier?.carrier ?? "—",
                sub: worstCarrier ? `${worstCarrier.overchargeRate}% over billed` : "No data",
                color: "border-l-red-500",
              },
              {
                label: "Best Compliance",
                value: bestCarrier?.carrier ?? "—",
                sub: bestCarrier ? `${bestCarrier.correctRate}% correct` : "No data",
                color: "border-l-emerald-500",
              },
              {
                label: "Total Overcharges",
                value: `$${(totalDiff/100000).toFixed(2)}L`,
                sub: `${caseList.filter(c=>(c.diff??0)>0).length} cases`,
                color: "border-l-amber-500",
              },
              {
                label: "Carriers Tracked",
                value: String(carrierStats.length),
                sub: `${caseList.length} cases total`,
                color: "border-l-blue-500",
              },
            ].map(({ label, value, sub, color }) => (
              <Card key={label} className={`border-l-4 ${color}`}>
                <CardContent className="pt-5">
                  <p className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium">{label}</p>
                  <p className="mt-2 text-lg font-bold text-zoiko-navy">{value}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">{sub}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
