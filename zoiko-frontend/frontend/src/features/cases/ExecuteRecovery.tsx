import { useQuery } from "@tanstack/react-query";
import { zoikoApi } from "@/api/zoiko";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCurrency } from "@/utils/cn";
import { cn } from "@/utils/cn";
import { CheckCircle2, Clock, TrendingUp, Zap, Lock, AlertCircle, ExternalLink } from "lucide-react";
import { Link } from "react-router-dom";

const FUNNEL_STEPS = [
  { label: "Approved Cases",       count: 47, amount: 480000, color: "bg-purple-500",  pct: 100 },
  { label: "Tokens Issued",        count: 44, amount: 453000, color: "bg-blue-500",    pct: 94  },
  { label: "Gates Passed (8/8)",   count: 40, amount: 421000, color: "bg-indigo-500",  pct: 85  },
  { label: "Carrier Connected",    count: 38, amount: 405000, color: "bg-amber-500",   pct: 81  },
  { label: "Credit Memo Issued",   count: 32, amount: 358000, color: "bg-orange-500",  pct: 68  },
  { label: "Reconciled (ACR)",     count: 27, amount: 270000, color: "bg-emerald-500", pct: 57  },
];

const MOCK_RECOVERIES = [
  { case_id: "case_0002", carrier: "BlueDart",  amount: 4500,  currency: "INR", status: "OUTCOME_RECORDED", acr: "0x4a3f8e", date: "2025-01-15" },
  { case_id: "case_0004", carrier: "Delhivery", amount: 3200,  currency: "INR", status: "DISPATCHED",   acr: "0x7c2d1b", date: "2025-01-14" },
  { case_id: "case_0006", carrier: "FedEx",     amount: 8900,  currency: "INR", status: "OUTCOME_RECORDED", acr: "0x9e5a4f", date: "2025-01-13" },
  { case_id: "case_0008", carrier: "DTDC",      amount: 2100,  currency: "INR", status: "DISPATCHED",   acr: "0x1b8c3d", date: "2025-01-12" },
  { case_id: "case_0010", carrier: "BlueDart",  amount: 6700,  currency: "INR", status: "OUTCOME_RECORDED", acr: "0x6f2e9a", date: "2025-01-11" },
  { case_id: "case_0012", carrier: "Ekart",     amount: 1850,  currency: "INR", status: "DISPATCHED",   acr: "0x3a7b5c", date: "2025-01-10" },
];

const GATES = [
  { num: 1, name: "Token signature",   desc: "Ed25519 verifies against tenant public key" },
  { num: 2, name: "Token expiry",      desc: "exp claim still in future (15-min TTL)" },
  { num: 3, name: "Tenant binding",    desc: "H(tenant_id) matches token binding" },
  { num: 4, name: "Scope check",       desc: "Token scope = EXECUTE" },
  { num: 5, name: "Sanctions screen",  desc: "Counterparty not on OFAC/UN lists" },
  { num: 6, name: "FX lock",           desc: "Exchange rate locked for transaction" },
  { num: 7, name: "Connector cert",    desc: "Carrier connector certification valid" },
  { num: 8, name: "Idempotency key",   desc: "Key not previously seen (replay guard)" },
];

export default function ExecuteRecovery() {
  const { data: tokens } = useQuery({ queryKey: ["tokens"], queryFn: () => zoikoApi.listTokens({ status: "ACTIVE" }) });
  const { data: cases } = useQuery({ queryKey: ["cases"], queryFn: () => zoikoApi.listCases() });

  const approvedCases   = cases?.filter(c => ["EXECUTION_READY", "DISPATCHED", "OUTCOME_RECORDED"].includes(c.state)) ?? [];
  const executedCases   = cases?.filter(c => ["DISPATCHED", "OUTCOME_RECORDED"].includes(c.state)) ?? [];
  const reconciledCases = cases?.filter(c => c.state === "OUTCOME_RECORDED") ?? [];
  const pendingCases    = cases?.filter(c => c.state === "EXECUTION_READY") ?? [];

  const approvedAmt   = approvedCases.reduce((s, c) => s + c.diff, 0) || 480000;
  const executedAmt   = executedCases.reduce((s, c) => s + c.diff, 0) || 320000;
  const reconciledAmt = reconciledCases.reduce((s, c) => s + c.diff, 0) || 270000;
  const pendingAmt    = pendingCases.reduce((s, c) => s + c.diff, 0) || 160000;

  const activeTokens = tokens ?? [];

  return (
    <div className="space-y-6">

      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-zoiko-navy">Recovery Tracker</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Monitor money flow from approved cases through 8-gate execution to reconciled ACR records.
        </p>
      </div>

      {/* 4 KPI cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="border-l-4 border-l-purple-500">
          <CardContent className="pt-5">
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium">Approved</p>
            <p className="mt-2 text-2xl font-bold text-purple-700">{formatCurrency(approvedAmt)}</p>
            <p className="mt-1 text-xs text-muted-foreground flex items-center gap-1">
              <CheckCircle2 className="h-3 w-3" /> {approvedCases.length || 47} cases
            </p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-blue-500">
          <CardContent className="pt-5">
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium">Executed</p>
            <p className="mt-2 text-2xl font-bold text-blue-700">{formatCurrency(executedAmt)}</p>
            <p className="mt-1 text-xs text-muted-foreground flex items-center gap-1">
              <Zap className="h-3 w-3" /> {executedCases.length || 30} cases · 67%
            </p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-emerald-500">
          <CardContent className="pt-5">
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium">Reconciled</p>
            <p className="mt-2 text-2xl font-bold text-emerald-700">{formatCurrency(reconciledAmt)}</p>
            <p className="mt-1 text-xs text-muted-foreground flex items-center gap-1">
              <Lock className="h-3 w-3" /> {reconciledCases.length || 27} ACR locked
            </p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-amber-500">
          <CardContent className="pt-5">
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium">Pending</p>
            <p className="mt-2 text-2xl font-bold text-amber-700">{formatCurrency(pendingAmt)}</p>
            <p className="mt-1 text-xs text-muted-foreground flex items-center gap-1">
              <Clock className="h-3 w-3" /> {pendingCases.length || 17} awaiting execution
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* Recovery Funnel */}
        <div className="lg:col-span-2">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Recovery Funnel</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {FUNNEL_STEPS.map((step, i) => (
                <div key={i} className="flex items-center gap-3">
                  <div className="w-36 text-xs text-muted-foreground text-right flex-shrink-0">{step.label}</div>
                  <div className="flex-1 relative h-8 bg-secondary rounded-lg overflow-hidden">
                    <div
                      className={cn("h-full rounded-lg transition-all", step.color)}
                      style={{ width: `${step.pct}%` }}
                    />
                    <div className="absolute inset-0 flex items-center px-3 gap-3">
                      <span className="text-xs font-bold text-white drop-shadow">{step.count} cases</span>
                      <span className="text-xs text-white/80 drop-shadow">{formatCurrency(step.amount)}</span>
                    </div>
                  </div>
                  <div className="w-10 text-xs font-bold text-muted-foreground text-right flex-shrink-0">{step.pct}%</div>
                </div>
              ))}
              <div className="pt-2 flex items-center gap-2 text-xs text-muted-foreground border-t">
                <TrendingUp className="h-3.5 w-3.5 text-emerald-600" />
                <span>57% end-to-end reconciliation rate · ₹2.7L recovered out of ₹4.8L approved</span>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* 8-Gate Checklist */}
        <div>
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">8 Execution Gates</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {GATES.map(g => (
                  <div key={g.num} className="flex items-start gap-2.5 p-2 rounded-lg bg-emerald-50 border border-emerald-100">
                    <div className="h-5 w-5 rounded-full bg-emerald-500 text-white text-[9px] font-bold flex items-center justify-center flex-shrink-0 mt-0.5">{g.num}</div>
                    <div>
                      <p className="text-xs font-semibold text-emerald-800">{g.name}</p>
                      <p className="text-[10px] text-emerald-600">{g.desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Active Tokens */}
      {activeTokens.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
              Active Tokens — Ready for Execution ({activeTokens.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {activeTokens.map(t => (
                <div key={t.id} className="rounded-lg border bg-amber-50 border-amber-200 px-4 py-3 flex items-center justify-between">
                  <div>
                    <code className="text-xs text-muted-foreground">{t.id}</code>
                    <p className="text-sm font-semibold mt-0.5">{t.action} · {formatCurrency(t.amount, t.currency)}</p>
                    <p className="text-xs text-muted-foreground">case {t.case_id} · expires {new Date(t.exp).toLocaleTimeString()}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-bold px-2 py-1 rounded-full bg-amber-200 text-amber-800">ACTIVE</span>
                    <AlertCircle className="h-4 w-4 text-amber-600" />
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Recent Recoveries Table */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Recent Recoveries</CardTitle>
        </CardHeader>
        <CardContent>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-[10px] uppercase tracking-wide text-muted-foreground">
                <th className="text-left pb-2 font-medium">Case</th>
                <th className="text-left pb-2 font-medium">Carrier</th>
                <th className="text-right pb-2 font-medium">Recovered</th>
                <th className="text-left pb-2 font-medium">ACR Hash</th>
                <th className="text-left pb-2 font-medium">Date</th>
                <th className="text-left pb-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {MOCK_RECOVERIES.map(r => (
                <tr key={r.case_id} className="hover:bg-secondary/30">
                  <td className="py-3">
                    <Link to={`/cases/${r.case_id}`} className="text-xs font-mono text-zoiko-blue hover:underline flex items-center gap-1">
                      {r.case_id} <ExternalLink className="h-2.5 w-2.5" />
                    </Link>
                  </td>
                  <td className="py-3 text-xs">{r.carrier}</td>
                  <td className="py-3 text-right text-xs font-semibold text-emerald-700">{formatCurrency(r.amount, r.currency)}</td>
                  <td className="py-3">
                    <code className="text-[10px] bg-secondary px-1.5 py-0.5 rounded text-muted-foreground">{r.acr}…</code>
                  </td>
                  <td className="py-3 text-xs text-muted-foreground">{r.date}</td>
                  <td className="py-3">
                    <span className={cn(
                      "text-[10px] font-bold px-2 py-0.5 rounded-full",
                      r.status === "OUTCOME_RECORDED" ? "bg-emerald-100 text-emerald-700" : "bg-blue-100 text-blue-700"
                    )}>
                      {r.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}
