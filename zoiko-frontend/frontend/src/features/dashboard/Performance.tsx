import { useQuery } from "@tanstack/react-query";
import { zoikoApi } from "@/api/zoiko";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCurrency } from "@/utils/cn";
import { TrendingUp, TrendingDown, Package, ShieldCheck } from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, LineChart, Line, Legend,
} from "recharts";
import type { Case } from "@/types";

const CARRIER_COLORS: Record<string, string> = {
  BlueDart:  "#1d4ed8",
  DHL:       "#ea580c",
  FedEx:     "#7c3aed",
  Delhivery: "#16a34a",
  DTDC:      "#dc2626",
  XpressBees:"#0891b2",
  Other:     "#94a3b8",
};

function getColor(carrier: string): string {
  return CARRIER_COLORS[carrier] ?? "#94a3b8";
}

function buildMonthlySpend(cases: Case[]) {
  const map: Record<string, { month: string; spend: number; savings: number }> = {};
  for (const c of cases) {
    const month = new Date(c.opened_at).toLocaleString("default", { month: "short" });
    if (!map[month]) map[month] = { month, spend: 0, savings: 0 };
    map[month].spend += c.amount ?? 0;
    if (["EXECUTION_READY","DISPATCHED","OUTCOME_RECORDED","CLOSED"].includes(c.state)) {
      map[month].savings += c.diff ?? 0;
    }
  }
  return Object.values(map);
}

function buildCarrierMix(cases: Case[]) {
  const byMonth: Record<string, Record<string, number>> = {};
  const carriers = new Set<string>();
  for (const c of cases) {
    const month = new Date(c.opened_at).toLocaleString("default", { month: "short" });
    const carrier = c.carrier || "Other";
    carriers.add(carrier);
    if (!byMonth[month]) byMonth[month] = {};
    byMonth[month][carrier] = (byMonth[month][carrier] ?? 0) + (c.amount ?? 0);
  }
  const months = Object.keys(byMonth);
  return {
    data: months.map(month => {
      const total = Object.values(byMonth[month]).reduce((s, v) => s + v, 0) || 1;
      const row: Record<string, string | number> = { month };
      for (const c of carriers) row[c] = Math.round(((byMonth[month][c] ?? 0) / total) * 100);
      return row;
    }),
    carriers: [...carriers],
  };
}

function buildOverchargeRate(cases: Case[]) {
  const byMonth: Record<string, { total: number; over: number }> = {};
  for (const c of cases) {
    const month = new Date(c.opened_at).toLocaleString("default", { month: "short" });
    if (!byMonth[month]) byMonth[month] = { total: 0, over: 0 };
    byMonth[month].total += 1;
    if ((c.diff ?? 0) > 0) byMonth[month].over += 1;
  }
  return Object.entries(byMonth).map(([month, v]) => ({
    month,
    rate: parseFloat(((v.over / (v.total || 1)) * 100).toFixed(1)),
  }));
}

export default function Performance() {
  const { data: stats } = useQuery({ queryKey: ["stats"], queryFn: zoikoApi.getStats });
  const { data: cases = [] } = useQuery({ queryKey: ["cases"], queryFn: () => zoikoApi.listCases() });

  const totalCases   = stats?.total_cases   ?? cases.length;
  const totalSaved   = stats?.total_recovered ?? 0;
  const totalSpend   = (cases as Case[]).reduce((s, c) => s + (c.amount ?? 0), 0);
  const auditCoverage = totalCases > 0 ? 100 : 0;

  const spendData    = buildMonthlySpend(cases as Case[]);
  const { data: carrierMix, carriers } = buildCarrierMix(cases as Case[]);
  const overchargeRate = buildOverchargeRate(cases as Case[]);

  const kpis = [
    { label: "Total Freight Spend",  value: formatCurrency(totalSpend),    sub: `${cases.length} invoices`,   icon: Package,      color: "border-l-blue-500",    text: "text-blue-700"    },
    { label: "Total Recovered",      value: formatCurrency(totalSaved),     sub: `${stats?.approved ?? 0} approved`, icon: TrendingUp,   color: "border-l-emerald-500", text: "text-emerald-700" },
    { label: "Total Cases",          value: String(totalCases),             sub: `${stats?.pending_approval ?? 0} pending`, icon: ShieldCheck, color: "border-l-purple-500",  text: "text-purple-700"  },
    { label: "Audit Coverage",       value: `${auditCoverage}%`,            sub: "Target: 100%",               icon: TrendingDown, color: "border-l-amber-500",   text: "text-amber-700"   },
  ];

  return (
    <div className="space-y-6">

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-zoiko-navy">Performance Overview</h1>
          <p className="text-sm text-muted-foreground mt-1">Freight spend analytics · live data</p>
        </div>
        <span className="text-[10px] font-bold px-3 py-1.5 rounded-full bg-zoiko-navy text-white">
          LIVE DATA
        </span>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {kpis.map(({ label, value, sub, icon: Icon, color, text }) => (
          <Card key={label} className={`border-l-4 ${color}`}>
            <CardContent className="pt-5">
              <div className="flex items-start justify-between">
                <p className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium">{label}</p>
                <Icon className="h-4 w-4 text-muted-foreground/50" />
              </div>
              <p className={`mt-2 text-2xl font-bold ${text}`}>{value}</p>
              <p className="mt-1 text-xs text-muted-foreground">{sub}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Two charts side by side */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

        {/* Spend vs Savings */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Monthly Spend vs Audit Savings</CardTitle>
          </CardHeader>
          <CardContent>
            {spendData.length === 0 ? (
              <div className="flex items-center justify-center h-[240px] text-sm text-muted-foreground">
                No data yet — create cases to see spend analytics
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={spendData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 10 }} width={60}
                    tickFormatter={(v: number) => `₹${(v / 100000).toFixed(0)}L`} />
                  <Tooltip
                    formatter={(v: number, name: string) => [
                      formatCurrency(v),
                      name === "spend" ? "Total Spend" : "Audit Savings",
                    ]}
                  />
                  <Legend formatter={(v) => v === "spend" ? "Total Spend" : "Audit Savings"} />
                  <Bar dataKey="spend"   fill="#1d4ed8" radius={[4,4,0,0]} />
                  <Bar dataKey="savings" fill="#10b981" radius={[4,4,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        {/* Carrier Mix */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Carrier Spend Mix (%)</CardTitle>
          </CardHeader>
          <CardContent>
            {carrierMix.length === 0 ? (
              <div className="flex items-center justify-center h-[240px] text-sm text-muted-foreground">
                No carrier data yet
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={carrierMix} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 10 }} width={35} />
                  <Tooltip formatter={(v: number) => [`${v}%`]} />
                  <Legend />
                  {carriers.map(c => (
                    <Bar key={c} dataKey={c} stackId="mix" fill={getColor(c)} />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Overcharge rate trend */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Invoice Overcharge Rate by Month</CardTitle>
        </CardHeader>
        <CardContent>
          {overchargeRate.length === 0 ? (
            <div className="flex items-center justify-center h-[180px] text-sm text-muted-foreground">
              No overcharge rate data yet
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={overchargeRate} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 10 }} width={35} domain={[0, 100]}
                  tickFormatter={(v: number) => `${v}%`} />
                <Tooltip formatter={(v: number) => [`${v}%`, "Overcharge Rate"]} />
                <Line type="monotone" dataKey="rate" stroke="#ef4444" strokeWidth={2.5}
                  dot={{ r: 5, fill: "#ef4444" }} activeDot={{ r: 7 }} />
              </LineChart>
            </ResponsiveContainer>
          )}
          <p className="text-xs text-muted-foreground text-center mt-2">
            % of cases with billing discrepancy · computed from live case data
          </p>
        </CardContent>
      </Card>

      {/* Recent cases table */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Recent Case Outcomes</CardTitle>
        </CardHeader>
        <CardContent>
          {cases.length > 0 ? (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-[10px] uppercase tracking-wide text-muted-foreground">
                  <th className="text-left pb-2 font-medium">Invoice</th>
                  <th className="text-left pb-2 font-medium">Carrier</th>
                  <th className="text-right pb-2 font-medium">Billed</th>
                  <th className="text-right pb-2 font-medium">Overcharge</th>
                  <th className="text-left pb-2 font-medium pl-4">State</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {(cases as Case[]).slice(0, 8).map(c => (
                  <tr key={c.id} className="hover:bg-secondary/30">
                    <td className="py-2.5 font-medium text-xs">{c.shipment_ref || c.id.slice(0, 8)}</td>
                    <td className="py-2.5 text-xs">{c.carrier || "—"}</td>
                    <td className="py-2.5 text-right text-xs">{formatCurrency(c.amount || 0)}</td>
                    <td className="py-2.5 text-right text-xs font-semibold text-emerald-600">{formatCurrency(c.diff || 0)}</td>
                    <td className="py-2.5 pl-4">
                      <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-secondary">
                        {c.state.replace(/_/g," ")}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="py-8 text-center text-sm text-muted-foreground">
              No cases yet — upload an invoice to see live data.
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
