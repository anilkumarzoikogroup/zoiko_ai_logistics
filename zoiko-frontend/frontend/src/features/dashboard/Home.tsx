import { useQuery } from "@tanstack/react-query";
import { zoikoApi } from "@/api/zoiko";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCurrency } from "@/utils/cn";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import {
  Activity, CheckCircle2, Zap, AlertTriangle, Clock,
  ArrowRight, Circle, ChevronRight,
} from "lucide-react";
import { cn } from "@/utils/cn";

const PIPELINE_STAGES = [
  { id: "ingested",    label: "Ingested",          color: "bg-blue-500",    count: 184, drop: null },
  { id: "validated",   label: "Validated",          color: "bg-indigo-500",  count: 182, drop: 2 },
  { id: "canonical",   label: "Canonicalized",      color: "bg-violet-500",  count: 181, drop: 1 },
  { id: "case_opened", label: "Case Opened",        color: "bg-purple-500",  count: 23,  drop: 158 },
  { id: "evidence",    label: "Evidence Bundled",   color: "bg-amber-500",   count: 21,  drop: 2 },
  { id: "reasoning",   label: "AI Reasoned",        color: "bg-orange-500",  count: 20,  drop: 1 },
  { id: "approved",    label: "Approved",           color: "bg-emerald-500", count: 18,  drop: 2 },
  { id: "executed",    label: "Recovered",          color: "bg-green-600",   count: 15,  drop: 3 },
];

const INFLIGHT = [
  { id: "case_0001", carrier: "BlueDart",  ref: "HYD-WAR-20250115-001", stage: "APPROVAL_PENDING", amount: 12500, latency: "1.2s",  conf: 0.96 },
  { id: "case_0003", carrier: "Delhivery", ref: "MUM-PUN-20250116-003", stage: "FINDING_GENERATED",     amount: 8800,  latency: "0.8s",  conf: 0.89 },
  { id: "case_0005", carrier: "FedEx",     ref: "DEL-JAI-20250117-005", stage: "EVIDENCE_PENDING",amount: 15200, latency: "2.1s", conf: 0.78 },
  { id: "case_0007", carrier: "DTDC",      ref: "CHE-BLR-20250118-007", stage: "FINDING_GENERATED",     amount: 6400,  latency: "0.6s",  conf: 0.91 },
];

const HEALTH_STAGES = [
  { label: "Ingestion",    p95: 120 },
  { label: "Validation",   p95: 45  },
  { label: "Canonicalize", p95: 30  },
  { label: "Case Open",    p95: 85  },
  { label: "Evidence",     p95: 340 },
  { label: "AI Reason",    p95: 210 },
  { label: "Governance",   p95: 95  },
  { label: "Execution",    p95: 180 },
];

const RECENT_ERRORS = [
  { time: "2 min ago", severity: "warning", msg: "BlueDart connector: 429 rate limit — retrying" },
  { time: "18 min ago", severity: "info",    msg: "Token tok_a4f3 expired before redemption" },
  { time: "1 hr ago",  severity: "error",   msg: "Ed25519 signature verify fail: case_0019" },
];

function StageChip({ stage }: { stage: string }) {
  const colors: Record<string, string> = {
    "NEW": "bg-blue-100 text-blue-700",
    "EVIDENCE_PENDING": "bg-amber-100 text-amber-700",
    "FINDING_GENERATED": "bg-violet-100 text-violet-700",
    "APPROVAL_PENDING": "bg-orange-100 text-orange-700",
    "EXECUTION_READY": "bg-emerald-100 text-emerald-700",
    "DISPATCHED": "bg-green-100 text-green-700",
  };
  return (
    <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded-full", colors[stage] || "bg-gray-100 text-gray-700")}>
      {stage.replace("_", " ")}
    </span>
  );
}

export default function Home() {
  const { data: cases } = useQuery({ queryKey: ["cases"], queryFn: () => zoikoApi.listCases() });
  const { data: stats } = useQuery({ queryKey: ["stats"],  queryFn: zoikoApi.getStats, refetchInterval: 5000 });

  const reviewCount   = cases?.filter(c => ["NEW", "EVIDENCE_PENDING", "FINDING_GENERATED"].includes(c.state)).length ?? 0;
  const approvalCount = cases?.filter(c => c.state === "APPROVAL_PENDING").length ?? 0;
  const executedCount = cases?.filter(c => ["DISPATCHED", "OUTCOME_RECORDED"].includes(c.state)).length ?? 0;
  const totalCases    = stats?.total_cases ?? cases?.length ?? 184;
  const recovered     = stats?.total_recovered ?? (executedCount * 4500);

  return (
    <div className="space-y-6">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-zoiko-navy">Live Pipeline Monitor</h1>
            <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-700 text-xs font-bold">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
              LIVE
            </span>
          </div>
          <p className="text-sm text-muted-foreground mt-1">Real-time view of invoices flowing through every stage · auto-refreshing every 5s</p>
        </div>
        <Link to="/cases/new">
          <Button size="sm" className="gap-2"><Activity className="h-4 w-4" /> Submit Invoice</Button>
        </Link>
      </div>

      {/* 6 KPI cards */}
      <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
        <Card className="border-l-4 border-l-blue-500">
          <CardContent className="pt-4 pb-4">
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium">Ingested</p>
            <p className="mt-1 text-2xl font-bold text-zoiko-navy">{totalCases}</p>
            <p className="mt-0.5 text-xs text-muted-foreground">invoices today</p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-indigo-500">
          <CardContent className="pt-4 pb-4">
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium">Validated</p>
            <p className="mt-1 text-2xl font-bold text-indigo-700">98.9%</p>
            <p className="mt-0.5 text-xs text-muted-foreground">pass rate</p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-amber-500">
          <CardContent className="pt-4 pb-4">
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium">Cases Opened</p>
            <p className="mt-1 text-2xl font-bold text-amber-600">{approvalCount + reviewCount}</p>
            <p className="mt-0.5 text-xs text-muted-foreground">overcharges found</p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-purple-500">
          <CardContent className="pt-4 pb-4">
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium">Approved</p>
            <p className="mt-1 text-2xl font-bold text-purple-700">{stats?.approved ?? 18}</p>
            <p className="mt-0.5 text-xs text-muted-foreground">manager sign-off</p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-emerald-500">
          <CardContent className="pt-4 pb-4">
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium">Recovered</p>
            <p className="mt-1 text-2xl font-bold text-emerald-600">{formatCurrency(recovered > 0 ? recovered : 84000)}</p>
            <p className="mt-0.5 text-xs text-muted-foreground">money back</p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-cyan-500">
          <CardContent className="pt-4 pb-4">
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium">Avg Latency</p>
            <p className="mt-1 text-2xl font-bold text-cyan-700">1.2s</p>
            <p className="mt-0.5 text-xs text-muted-foreground">end-to-end P50</p>
          </CardContent>
        </Card>
      </div>

      {/* 8-Stage Invoice Flow Diagram */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Invoice Flow — 8 Stages</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-1 overflow-x-auto pb-2">
            {PIPELINE_STAGES.map((stage, idx) => (
              <div key={stage.id} className="flex items-center gap-1 flex-shrink-0">
                <div className="flex flex-col items-center gap-1.5">
                  <div className={cn("h-10 w-10 rounded-full flex items-center justify-center text-white text-xs font-bold", stage.color)}>
                    {idx + 1}
                  </div>
                  <p className="text-[10px] text-center font-medium leading-tight max-w-[60px]">{stage.label}</p>
                  <p className="text-[11px] font-bold text-zoiko-navy">{stage.count}</p>
                </div>
                {idx < PIPELINE_STAGES.length - 1 && (
                  <div className="flex flex-col items-center mx-1 flex-shrink-0">
                    <ChevronRight className="h-4 w-4 text-muted-foreground/50" />
                    {PIPELINE_STAGES[idx + 1].drop != null && PIPELINE_STAGES[idx + 1].drop! > 0 && (
                      <span className="text-[9px] text-destructive font-medium">-{PIPELINE_STAGES[idx + 1].drop}</span>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
          <div className="mt-3 flex items-center gap-4 text-xs text-muted-foreground border-t pt-3">
            <span className="flex items-center gap-1"><Circle className="h-2 w-2 fill-blue-500 text-blue-500" /> Numbers = invoices at each stage today</span>
            <span className="flex items-center gap-1 text-destructive"><Circle className="h-2 w-2 fill-destructive text-destructive" /> Red = drop count between stages</span>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* Invoices in Flight */}
        <div className="lg:col-span-2">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <CardTitle className="text-base">Invoices in Flight</CardTitle>
              <Link to="/cases"><Button variant="ghost" size="sm" className="text-xs gap-1">View all <ArrowRight className="h-3 w-3" /></Button></Link>
            </CardHeader>
            <CardContent>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-[10px] uppercase tracking-wide text-muted-foreground">
                    <th className="text-left pb-2 font-medium">Case</th>
                    <th className="text-left pb-2 font-medium">Carrier</th>
                    <th className="text-left pb-2 font-medium">Stage</th>
                    <th className="text-right pb-2 font-medium">Amount</th>
                    <th className="text-right pb-2 font-medium">Latency</th>
                    <th className="text-right pb-2 font-medium">Conf.</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {(cases || INFLIGHT).slice(0, 6).map((c: any) => (
                    <tr key={c.id} className="hover:bg-secondary/30">
                      <td className="py-2.5">
                        <Link to={`/cases/${c.id}`} className="text-xs font-mono text-zoiko-blue hover:underline">{c.id}</Link>
                      </td>
                      <td className="py-2.5 text-xs">{c.carrier}</td>
                      <td className="py-2.5"><StageChip stage={c.state || c.stage} /></td>
                      <td className="py-2.5 text-right text-xs font-medium">{formatCurrency(c.amount, c.currency || "INR")}</td>
                      <td className="py-2.5 text-right text-xs text-muted-foreground">{c.latency || "0.9s"}</td>
                      <td className="py-2.5 text-right">
                        <span className={cn("text-xs font-medium", (c.confidence ?? 0.9) >= 0.9 ? "text-emerald-600" : "text-amber-600")}>
                          {((c.confidence ?? 0.9) * 100).toFixed(0)}%
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </div>

        {/* Pipeline Health */}
        <div>
          <Card className="h-full">
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Pipeline Health</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">

              {/* Recent errors */}
              <div className="space-y-2">
                {RECENT_ERRORS.map((e, i) => (
                  <div key={i} className={cn(
                    "rounded-lg px-3 py-2 text-xs border",
                    e.severity === "error" ? "bg-red-50 border-red-200 text-red-800" :
                    e.severity === "warning" ? "bg-amber-50 border-amber-200 text-amber-800" :
                    "bg-blue-50 border-blue-200 text-blue-800"
                  )}>
                    <div className="flex items-center gap-1.5 mb-0.5">
                      <AlertTriangle className="h-3 w-3 flex-shrink-0" />
                      <span className="font-semibold capitalize">{e.severity}</span>
                      <span className="ml-auto text-[10px] opacity-70 flex items-center gap-0.5"><Clock className="h-2.5 w-2.5" />{e.time}</span>
                    </div>
                    <p>{e.msg}</p>
                  </div>
                ))}
              </div>

              {/* Stage latency bars */}
              <div>
                <p className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium mb-2">Stage Latency (P95)</p>
                <div className="space-y-1.5">
                  {HEALTH_STAGES.map(s => (
                    <div key={s.label} className="flex items-center gap-2">
                      <span className="text-[10px] w-20 text-muted-foreground flex-shrink-0">{s.label}</span>
                      <div className="flex-1 h-1.5 bg-secondary rounded-full overflow-hidden">
                        <div
                          className={cn("h-full rounded-full", s.p95 > 300 ? "bg-amber-500" : "bg-emerald-500")}
                          style={{ width: `${Math.min(100, (s.p95 / 400) * 100)}%` }}
                        />
                      </div>
                      <span className="text-[10px] text-muted-foreground w-10 text-right flex-shrink-0">{s.p95}ms</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-lg bg-emerald-50 border border-emerald-200 px-3 py-2 flex items-center gap-2 text-xs text-emerald-700">
                <CheckCircle2 className="h-3.5 w-3.5 flex-shrink-0" />
                All systems operational · OPA healthy · Kafka lag 0ms
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Action banners */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {reviewCount > 0 && (
          <Link to="/analyst">
            <div className="rounded-xl bg-zoiko-blue text-white p-4 flex items-center justify-between hover:opacity-90 transition-opacity cursor-pointer">
              <div>
                <p className="font-semibold text-sm">{reviewCount} awaiting analyst review</p>
                <p className="text-xs text-white/75 mt-0.5">Review and propose recovery</p>
              </div>
              <ArrowRight className="h-5 w-5 flex-shrink-0" />
            </div>
          </Link>
        )}
        {approvalCount > 0 && (
          <Link to="/manager">
            <div className="rounded-xl bg-zoiko-purple text-white p-4 flex items-center justify-between hover:opacity-90 transition-opacity cursor-pointer">
              <div>
                <p className="font-semibold text-sm">{approvalCount} pending manager approval</p>
                <p className="text-xs text-white/75 mt-0.5">Approve or reject recoveries</p>
              </div>
              <ArrowRight className="h-5 w-5 flex-shrink-0" />
            </div>
          </Link>
        )}
        <Link to="/execute">
          <div className="rounded-xl bg-emerald-600 text-white p-4 flex items-center justify-between hover:opacity-90 transition-opacity cursor-pointer">
            <div>
              <p className="font-semibold text-sm flex items-center gap-2"><Zap className="h-4 w-4" /> Recovery Tracker</p>
              <p className="text-xs text-white/75 mt-0.5">Monitor money flow &amp; ACR locks</p>
            </div>
            <ArrowRight className="h-5 w-5 flex-shrink-0" />
          </div>
        </Link>
      </div>
    </div>
  );
}
