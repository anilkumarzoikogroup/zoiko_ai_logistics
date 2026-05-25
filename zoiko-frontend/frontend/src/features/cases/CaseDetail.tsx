import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { zoikoApi } from "@/api/zoiko";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { StateBadge, HashDisplay, LoadingSpinner } from "@/components/shared";
import { formatCurrency, formatDate, cn } from "@/utils/cn";
import {
  ArrowRight, UserCheck, CheckCircle2, Zap, Clock,
  FileText, Shield, Hash, Brain, Lock, AlertTriangle,
  ChevronRight, CircleDot, Circle,
} from "lucide-react";
import type { CaseState } from "@/types";

// Maps each state to how many pipeline stages are complete (1-indexed, spec §7.5)
const STATE_STAGE: Record<CaseState, number> = {
  NEW:               4,
  EVIDENCE_PENDING:  5,
  FINDING_GENERATED: 6,
  APPROVAL_PENDING:  7,
  EXECUTION_READY:   7,
  DISPATCHED:        8,
  OUTCOME_RECORDED:  8,
  CLOSED:            8,
  ABORTED:           6,
};

const PIPELINE_STAGES = [
  {
    num: 1, label: "Invoice Ingested", icon: FileText,
    done:    "Invoice received by ingestion service. SHA-256 hashed with domain tag `zoiko.ingestion.invoice.v1:`. Source record written to DB.",
    pending: "Waiting for invoice submission.",
  },
  {
    num: 2, label: "Validated", icon: Shield,
    done:    "Contract rate engine checked invoice amount vs agreed carrier rate. Overcharge detected — case flagged for dispute.",
    pending: "Validation not yet run.",
  },
  {
    num: 3, label: "Canonicalized", icon: Hash,
    done:    "JCS (RFC 8785) canonical form computed. Ed25519 signed with tenant key. Canonical invoice row locked — immutable.",
    pending: "Awaiting canonicalization.",
  },
  {
    num: 4, label: "Case Opened", icon: AlertTriangle,
    done:    "Dispute case created in case_orchestration. State machine initialized at NEW. Kafka event `zoiko.case.opened` published.",
    pending: "Case not opened yet.",
  },
  {
    num: 5, label: "Evidence Bundled", icon: FileText,
    done:    "Evidence items (BOL, Rate Sheet, Invoice) hashed and assembled into Merkle tree. Root hash locked. Kafka `evidence.bundled` published.",
    pending: "Evidence gathering in progress — BOL and rate sheet being collected.",
  },
  {
    num: 6, label: "AI Reasoned", icon: Brain,
    done:    "Reasoning engine scored the overcharge. Weighted confidence: fuel_charge (1.00 × 0.5) + accessorial (0.92 × 0.5) = 0.96. Finding hash computed.",
    pending: "Awaiting AI reasoning analysis.",
  },
  {
    num: 7, label: "Governance", icon: UserCheck,
    done:    "Analyst proposed recovery. Manager approved (Separation-of-Duties enforced: proposer ≠ approver). Ed25519-signed governance token issued with 15-min TTL.",
    pending: "Waiting for analyst proposal and manager approval.",
  },
  {
    num: 8, label: "Executed & ACR", icon: Lock,
    done:    "8 execution gates passed. Credit memo issued to carrier. Merkle tree over 8 artifacts sealed into Action Certification Record (WORM-locked).",
    pending: "Pending 8-gate execution gateway.",
  },
];

const NEXT_ACTION: Partial<Record<CaseState, {
  label: string; route: string; icon: React.ElementType; color: string; explain: string;
}>> = {
  NEW:               { label: "Analyst Review",   route: "/analyst",  icon: UserCheck,    color: "bg-zoiko-blue text-white",   explain: "An analyst must review this overcharge, verify the amount, and propose a credit memo recovery." },
  EVIDENCE_PENDING:  { label: "Analyst Review",   route: "/analyst",  icon: UserCheck,    color: "bg-zoiko-blue text-white",   explain: "Evidence is being collected automatically. Once complete, an analyst can propose recovery." },
  FINDING_GENERATED: { label: "Analyst Review",   route: "/analyst",  icon: UserCheck,    color: "bg-zoiko-blue text-white",   explain: "AI analysis complete. Open the Analyst Review queue to propose a recovery amount." },
  APPROVAL_PENDING:  { label: "Manager Approval", route: "/manager",  icon: CheckCircle2, color: "bg-zoiko-purple text-white", explain: "Analyst has proposed recovery. A manager (different person — SoD rule) must approve to issue the governance token." },
  EXECUTION_READY:   { label: "Execute Recovery", route: "/execute",  icon: Zap,          color: "bg-emerald-600 text-white",  explain: "Governance token is ACTIVE. Run the 8-gate execution gateway within the 15-min token window to issue the credit memo." },
};

export default function CaseDetail() {
  const { id = "" } = useParams();

  const c       = useQuery({ queryKey: ["case",         id], queryFn: () => zoikoApi.getCase(id) });
  const events  = useQuery({ queryKey: ["case-events",  id], queryFn: () => zoikoApi.getCaseEvents(id) });
  const ev      = useQuery({ queryKey: ["evidence",     id], queryFn: () => zoikoApi.getEvidence(id),         retry: false });
  const finding = useQuery({ queryKey: ["finding",      id], queryFn: () => zoikoApi.getFinding(id),          retry: false });
  const token   = useQuery({ queryKey: ["token-for-case", id], queryFn: () => zoikoApi.getTokenForCase(id),   retry: false });
  const val     = useQuery({ queryKey: ["validation",   id], queryFn: () => zoikoApi.getValidationForCase(id), retry: false });

  if (c.isLoading) return <LoadingSpinner />;
  if (!c.data)     return <p className="text-muted-foreground p-8">Case not found.</p>;
  const cs = c.data;

  const completedStages = STATE_STAGE[cs.state] ?? 4;
  const next = NEXT_ACTION[cs.state];

  return (
    <div className="space-y-6">

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
            <Link to="/cases" className="hover:underline">All Cases</Link>
            <ChevronRight className="h-3 w-3" />
            <code>{cs.id}</code>
          </div>
          <h1 className="text-2xl font-bold text-zoiko-navy">{cs.carrier} · {cs.shipment_ref}</h1>
          <p className="text-sm text-muted-foreground mt-1">Opened {formatDate(cs.opened_at)}</p>
        </div>
        <StateBadge state={cs.state} />
      </div>

      {/* PIPELINE FLOW — the core of this page */}
      <Card className="border-zoiko-navy/20 bg-zoiko-navy/2">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm text-zoiko-navy">Case Pipeline — Where is this case?</CardTitle>
        </CardHeader>
        <CardContent>
          {/* Stepper */}
          <div className="flex items-start gap-0 overflow-x-auto pb-2">
            {PIPELINE_STAGES.map((stage, i) => {
              const stageNum   = i + 1;
              const done       = stageNum < completedStages;
              const active     = stageNum === completedStages;
              const pending    = stageNum > completedStages;
              const Icon       = stage.icon;
              return (
                <div key={stage.num} className="flex items-start flex-1 min-w-0">
                  <div className="flex flex-col items-center gap-1.5 flex-1 min-w-[60px]">
                    <div className={cn(
                      "h-8 w-8 rounded-full flex items-center justify-center flex-shrink-0 transition-all",
                      done    ? "bg-emerald-500 text-white shadow-sm"  : "",
                      active  ? "bg-zoiko-navy text-white ring-2 ring-zoiko-navy ring-offset-2 shadow-md" : "",
                      pending ? "bg-muted text-muted-foreground/50"   : "",
                    )}>
                      {done ? <CheckCircle2 className="h-4 w-4" /> : <Icon className="h-4 w-4" />}
                    </div>
                    <span className={cn(
                      "text-[9px] text-center leading-tight max-w-[60px]",
                      done    ? "text-emerald-600 font-medium" : "",
                      active  ? "text-zoiko-navy font-bold"    : "",
                      pending ? "text-muted-foreground/60"     : "",
                    )}>
                      {stage.label}
                    </span>
                    {active && (
                      <span className="text-[8px] font-bold text-zoiko-navy bg-zoiko-navy/10 px-1.5 rounded-full">
                        {cs.state === "ABORTED" ? "STOPPED" : "NOW"}
                      </span>
                    )}
                  </div>
                  {i < PIPELINE_STAGES.length - 1 && (
                    <div className={cn("h-px mt-4 flex-1 mx-0.5", done ? "bg-emerald-400" : "bg-border")} />
                  )}
                </div>
              );
            })}
          </div>

          {/* Current stage explanation */}
          <div className={cn(
            "mt-4 rounded-lg border px-4 py-3",
            cs.state === "ABORTED" ? "bg-red-50 border-red-200" : "bg-zoiko-navy/5 border-zoiko-navy/20"
          )}>
            <div className="flex items-start gap-3">
              {cs.state === "ABORTED"
                ? <AlertTriangle className="h-4 w-4 text-red-600 flex-shrink-0 mt-0.5" />
                : <CircleDot className="h-4 w-4 text-zoiko-navy flex-shrink-0 mt-0.5" />
              }
              <div>
                <p className={cn("text-sm font-semibold", cs.state === "ABORTED" ? "text-red-700" : "text-zoiko-navy")}>
                  Stage {completedStages}: {PIPELINE_STAGES[completedStages - 1]?.label}
                  {" — "}
                  <span className="font-normal">
                    {cs.state === "OUTCOME_RECORDED" || cs.state === "CLOSED"
                      ? "All 8 stages complete. ACR locked in WORM index."
                      : PIPELINE_STAGES[completedStages - 1]?.done}
                  </span>
                </p>
                {next && (
                  <p className="text-xs text-muted-foreground mt-1">
                    <span className="font-semibold">Next: </span>{next.explain}
                  </p>
                )}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Next Action CTA */}
      {next && (
        <div className={cn("rounded-xl px-5 py-4 flex items-center justify-between gap-4", next.color)}>
          <div className="flex items-center gap-3">
            <next.icon className="h-6 w-6 flex-shrink-0" />
            <div>
              <p className="font-bold">Action required: {next.label}</p>
              <p className="text-sm opacity-80 mt-0.5">{next.explain}</p>
            </div>
          </div>
          <Link to={next.route} className="flex-shrink-0">
            <Button variant="secondary" size="sm" className="gap-1.5 font-semibold whitespace-nowrap">
              Go to {next.label} <ArrowRight className="h-3.5 w-3.5" />
            </Button>
          </Link>
        </div>
      )}

      {/* KPI row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card className="border-l-4 border-l-zoiko-blue">
          <CardContent className="pt-4 pb-4">
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium">Invoice Amount</p>
            <p className="text-xl font-bold mt-1">{formatCurrency(cs.amount, cs.currency)}</p>
            <p className="text-xs text-muted-foreground mt-0.5">Carrier billed</p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-red-500">
          <CardContent className="pt-4 pb-4">
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium">Overcharge</p>
            <p className="text-xl font-bold text-destructive mt-1">{formatCurrency(cs.diff, cs.currency)}</p>
            <p className="text-xs text-muted-foreground mt-0.5">Above contract rate</p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-emerald-500">
          <CardContent className="pt-4 pb-4">
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium">AI Confidence</p>
            <p className={cn("text-xl font-bold mt-1", (cs.confidence ?? 0) >= 0.9 ? "text-emerald-600" : "text-amber-600")}>
              {cs.confidence ? `${(cs.confidence * 100).toFixed(0)}%` : "—"}
            </p>
            <p className="text-xs text-muted-foreground mt-0.5">Overcharge detection</p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-amber-500">
          <CardContent className="pt-4 pb-4">
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium">Contract Amount</p>
            <p className="text-xl font-bold text-amber-600 mt-1">
              {val.data ? formatCurrency(val.data.contract_amount, cs.currency) : formatCurrency(cs.amount - cs.diff, cs.currency)}
            </p>
            <p className="text-xs text-muted-foreground mt-0.5">Agreed rate</p>
          </CardContent>
        </Card>
      </div>

      {/* Pipeline Artifacts — one card per completed phase */}
      <div className="space-y-4">
        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">Pipeline Artifacts</h2>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

          {/* Stage 2: Validation */}
          <Card className={completedStages >= 2 ? "" : "opacity-40"}>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Shield className="h-4 w-4 text-indigo-500" />
                  Stage 2 — Validation Result
                </CardTitle>
                {completedStages >= 2
                  ? <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">DONE</span>
                  : <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-muted text-muted-foreground">PENDING</span>
                }
              </div>
            </CardHeader>
            <CardContent>
              {val.data ? (
                <div className="space-y-2 text-sm">
                  <div className="flex items-center gap-3 rounded-lg bg-red-50 border border-red-200 px-3 py-2">
                    <AlertTriangle className="h-4 w-4 text-red-600 flex-shrink-0" />
                    <div>
                      <p className="font-semibold text-red-700">Validation {val.data.outcome}</p>
                      <p className="text-xs text-red-600 mt-0.5">{val.data.reason}</p>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div className="rounded border px-3 py-2 bg-secondary/40">
                      <p className="text-muted-foreground">Billed</p>
                      <p className="font-bold text-destructive">{formatCurrency(val.data.invoice_amount)}</p>
                    </div>
                    <div className="rounded border px-3 py-2 bg-secondary/40">
                      <p className="text-muted-foreground">Contract allows</p>
                      <p className="font-bold text-emerald-700">{formatCurrency(val.data.contract_amount)}</p>
                    </div>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground flex items-center gap-2">
                  <Clock className="h-4 w-4" /> Validation not yet run
                </p>
              )}
            </CardContent>
          </Card>

          {/* Stage 5: Evidence */}
          <Card className={completedStages >= 5 ? "" : "opacity-40"}>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm flex items-center gap-2">
                  <FileText className="h-4 w-4 text-amber-500" />
                  Stage 5 — Evidence Bundle
                </CardTitle>
                {completedStages >= 5
                  ? <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">DONE</span>
                  : <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-muted text-muted-foreground">PENDING</span>
                }
              </div>
            </CardHeader>
            <CardContent>
              {ev.data ? (
                <div className="space-y-2">
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div className="rounded border px-3 py-2 bg-secondary/40">
                      <p className="text-muted-foreground">Items</p>
                      <p className="font-bold">{ev.data.item_count} documents</p>
                    </div>
                    <div className="rounded border px-3 py-2 bg-secondary/40">
                      <p className="text-muted-foreground">Merkle root</p>
                      <HashDisplay value={ev.data.merkle_root} />
                    </div>
                  </div>
                  <div className="space-y-1">
                    {ev.data.items?.map(it => (
                      <div key={it.id} className="flex items-center gap-2 text-xs py-1 border-b last:border-0">
                        <CheckCircle2 className="h-3 w-3 text-emerald-500 flex-shrink-0" />
                        <span className="font-mono text-purple-700 w-24 flex-shrink-0">{it.item_type}</span>
                        <HashDisplay value={it.leaf_hash} />
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground flex items-center gap-2">
                  <Clock className="h-4 w-4" /> Evidence not yet collected
                </p>
              )}
            </CardContent>
          </Card>

          {/* Stage 6: AI Finding */}
          <Card className={completedStages >= 6 ? "" : "opacity-40"}>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Brain className="h-4 w-4 text-purple-500" />
                  Stage 6 — AI Reasoning
                </CardTitle>
                {completedStages >= 6
                  ? <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">DONE</span>
                  : <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-muted text-muted-foreground">PENDING</span>
                }
              </div>
            </CardHeader>
            <CardContent>
              {finding.data ? (
                <div className="space-y-3">
                  <div className="flex items-center gap-3">
                    <p className={cn("text-3xl font-bold", finding.data.confidence >= 0.9 ? "text-emerald-600" : "text-amber-600")}>
                      {(finding.data.confidence * 100).toFixed(0)}%
                    </p>
                    <div className="text-xs text-muted-foreground">
                      <p className="font-semibold text-foreground">Overcharge confidence</p>
                      <p>Weighted rule-based scoring</p>
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    {Object.entries(finding.data.trace).map(([k, v]) => (
                      <div key={k} className="flex items-center gap-2 text-xs rounded border px-2 py-1.5 bg-secondary/40">
                        <Circle className="h-2 w-2 text-purple-500 flex-shrink-0" />
                        <span className="font-mono text-purple-700 flex-1">{k}</span>
                        <span className="text-muted-foreground">conf {v.confidence.toFixed(2)} × wt {v.weight.toFixed(2)}</span>
                        <span className="font-semibold">{(v.confidence * v.weight).toFixed(3)}</span>
                      </div>
                    ))}
                  </div>
                  <HashDisplay value={finding.data.finding_hash} label="Finding hash" />
                </div>
              ) : (
                <p className="text-sm text-muted-foreground flex items-center gap-2">
                  <Clock className="h-4 w-4" /> AI analysis not yet run
                </p>
              )}
            </CardContent>
          </Card>

          {/* Stage 7: Governance Token */}
          <Card className={completedStages >= 7 ? "" : "opacity-40"}>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Lock className="h-4 w-4 text-emerald-500" />
                  Stage 7 — Governance Token
                </CardTitle>
                {completedStages >= 7
                  ? <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">ISSUED</span>
                  : <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-muted text-muted-foreground">PENDING</span>
                }
              </div>
            </CardHeader>
            <CardContent>
              {token.data ? (
                <div className="space-y-2 text-sm">
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div className="rounded border px-3 py-2 bg-secondary/40">
                      <p className="text-muted-foreground">Action</p>
                      <p className="font-bold font-mono text-xs">{token.data.action}</p>
                    </div>
                    <div className="rounded border px-3 py-2 bg-secondary/40">
                      <p className="text-muted-foreground">Recovery</p>
                      <p className="font-bold text-emerald-700">{formatCurrency(token.data.amount, token.data.currency)}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 rounded-lg bg-emerald-50 border border-emerald-200 px-3 py-2 text-xs">
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 flex-shrink-0" />
                    <span className="font-semibold text-emerald-700">{token.data.status}</span>
                    <span className="text-muted-foreground ml-auto">Expires {formatDate(token.data.exp)}</span>
                  </div>
                  <HashDisplay value={token.data.signature} label="Ed25519 sig" />
                </div>
              ) : (
                <p className="text-sm text-muted-foreground flex items-center gap-2">
                  <Clock className="h-4 w-4" /> Token not yet issued — case needs manager approval
                </p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Case Event Timeline */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Case Timeline</CardTitle>
        </CardHeader>
        <CardContent>
          {events.data && events.data.length > 0 ? (
            <ol className="relative border-l border-border ml-3 space-y-0">
              {events.data.map((e, i) => (
                <li key={e.id} className="pl-6 pb-5 last:pb-0 relative">
                  <div className={cn(
                    "absolute -left-2.5 top-0.5 h-5 w-5 rounded-full border-2 border-white flex items-center justify-center",
                    i === 0 ? "bg-zoiko-navy" : "bg-emerald-500"
                  )}>
                    {i === 0
                      ? <span className="h-1.5 w-1.5 rounded-full bg-white" />
                      : <CheckCircle2 className="h-3 w-3 text-white" />
                    }
                  </div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs text-muted-foreground">{formatDate(e.created_at)}</span>
                    {e.from_state && (
                      <><StateBadge state={e.from_state as any} /><ArrowRight className="h-3 w-3 text-muted-foreground" /></>
                    )}
                    <StateBadge state={e.to_state as any} />
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    by <span className="font-medium text-foreground">{e.actor}</span> · {e.reason.replace(/_/g, " ")}
                  </p>
                </li>
              ))}
            </ol>
          ) : (
            <p className="text-sm text-muted-foreground">No events recorded yet.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
