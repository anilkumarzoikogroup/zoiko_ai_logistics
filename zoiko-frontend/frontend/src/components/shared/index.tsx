import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { cn, shortHash } from "@/utils/cn";
import { Copy, Check } from "lucide-react";
import { useState } from "react";
import type { CaseState } from "@/types";

export function StateBadge({ state }: { state: CaseState }) {
  const map: Record<CaseState, { label: string; variant: "default" | "secondary" | "destructive" | "outline" | "success" | "warning" | "info" | "purple" }> = {
    NEW:               { label: "New",                variant: "info"        },
    EVIDENCE_PENDING:  { label: "Evidence Pending",   variant: "info"        },
    FINDING_GENERATED: { label: "AI Analyzed",        variant: "purple"      },
    APPROVAL_PENDING:  { label: "Pending Approval",   variant: "warning"     },
    EXECUTION_READY:   { label: "Execution Ready",    variant: "success"     },
    DISPATCHED:        { label: "Dispatched",         variant: "success"     },
    OUTCOME_RECORDED:  { label: "Outcome Recorded",   variant: "success"     },
    CLOSED:            { label: "Closed",             variant: "secondary"   },
    ABORTED:           { label: "Aborted",            variant: "destructive" },
  };
  const { label, variant } = map[state];
  return <Badge variant={variant}>{label}</Badge>;      
}

export function HashDisplay({ value, label, full = false }: { value: string; label?: string; full?: boolean }) {
  const [copied, setCopied] = useState(false);
  function copy() {
    navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }
  return (
    <div className="flex items-center gap-2 group">
      {label && <span className="text-xs text-muted-foreground">{label}</span>}
      <code className="rounded bg-muted px-1.5 py-0.5 text-xs font-mono break-all">
        {full ? value : shortHash(value, 10)}
      </code>
      <button
        onClick={copy}
        className="opacity-0 group-hover:opacity-100 transition-opacity"
        title="Copy"
      >
        {copied ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5 text-muted-foreground" />}
      </button>
    </div>
  );
}

export function StatCard({ label, value, sublabel, accent }: { label: string; value: string | number; sublabel?: string; accent?: "default" | "success" | "warning" | "info" }) {
  const accentClass = {
    default: "border-l-zoiko-navy",
    success: "border-l-emerald-600",
    warning: "border-l-amber-600",
    info: "border-l-zoiko-blue",
  }[accent || "default"];
  return (
    <Card className={cn("border-l-4", accentClass)}>
      <CardContent className="pt-6">
        <p className="text-xs uppercase tracking-wide text-muted-foreground font-medium">{label}</p>
        <p className="mt-2 text-3xl font-semibold">{value}</p>
        {sublabel && <p className="mt-1 text-xs text-muted-foreground">{sublabel}</p>}
      </CardContent>
    </Card>
  );
}

export function LoadingSpinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center py-12 text-muted-foreground gap-3">
      <div className="h-5 w-5 rounded-full border-2 border-current border-t-transparent animate-spin" />
      <span className="text-sm">{label}</span>
    </div>
  );
}

export function SkeletonLine({ className }: { className?: string }) {
  return <div className={cn("h-3 rounded-full bg-muted animate-pulse", className)} />;
}

export function SkeletonCard() {
  return (
    <div className="rounded-xl border bg-white p-5 space-y-3 shadow-sm">
      <div className="flex items-start justify-between">
        <div className="space-y-2 flex-1">
          <SkeletonLine className="w-1/3" />
          <SkeletonLine className="w-1/2 h-4" />
        </div>
        <SkeletonLine className="w-16 h-5 rounded-full ml-4" />
      </div>
      <div className="grid grid-cols-3 gap-3">
        <SkeletonLine className="h-8 rounded-lg" />
        <SkeletonLine className="h-8 rounded-lg" />
        <SkeletonLine className="h-8 rounded-lg" />
      </div>
      <SkeletonLine className="w-3/4" />
    </div>
  );
}

export function EmptyState({ title, description }: { title: string; description?: string }) {
  return (
    <div className="text-center py-12 text-muted-foreground">
      <p className="text-base font-medium text-foreground">{title}</p>
      {description && <p className="mt-1 text-sm">{description}</p>}
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="rounded-md border border-destructive/20 bg-destructive/5 px-4 py-3 text-sm text-destructive">
      {message}
    </div>
  );
}

export function PhaseBadge({ phase }: { phase: 0 | 1 | 2 | 3 | 4 | 5 }) {
  const colors = ["bg-zoiko-navy", "bg-zoiko-blue", "bg-zoiko-teal", "bg-zoiko-purple", "bg-zoiko-amber", "bg-orange-600"];
  return (
    <span className={cn("inline-flex items-center rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-white", colors[phase])}>
      Phase {phase}
    </span>
  );
}

const PIPELINE_STEPS = [
  { label: "Submit Invoice",   route: "/cases/new",  phase: 2 },
  { label: "Ingest & Hash",    route: "/ingestion",  phase: 2 },
  { label: "Validate",         route: "/validation", phase: 2 },
  { label: "Canonical Truth",  route: "/canonical",  phase: 2 },
  { label: "Evidence Bundle",  route: "/evidence",   phase: 3 },
  { label: "AI Reasoning",     route: "/reasoning",  phase: 3 },
  { label: "Governance",       route: "/governance", phase: 3 },
  { label: "Execute & ACR",    route: "/execute",    phase: 4 },
];

export function PipelineBanner({ currentRoute }: { currentRoute: string }) {
  const currentIndex = PIPELINE_STEPS.findIndex(s => currentRoute.startsWith(s.route));
  if (currentIndex === -1) return null;
  return (
    <div className="w-full bg-zoiko-navy/5 border border-zoiko-navy/10 rounded-lg px-4 py-3 mb-6">
      <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold mb-2">SC-001 Pipeline</p>
      <div className="flex items-center gap-0">
        {PIPELINE_STEPS.map((step, i) => {
          const done    = i < currentIndex;
          const active  = i === currentIndex;
          const future  = i > currentIndex;
          return (
            <div key={step.route} className="flex items-center flex-1 min-w-0">
              <div className={cn(
                "flex flex-col items-center gap-1 flex-1 min-w-0",
              )}>
                <div className={cn(
                  "h-6 w-6 rounded-full flex items-center justify-center text-[10px] font-bold flex-shrink-0 transition-colors",
                  done   ? "bg-emerald-600 text-white" : "",
                  active ? "bg-zoiko-navy text-white ring-2 ring-zoiko-navy ring-offset-1" : "",
                  future ? "bg-muted text-muted-foreground" : "",
                )}>
                  {done ? "✓" : i + 1}
                </div>
                <span className={cn(
                  "text-[9px] text-center leading-tight hidden sm:block truncate w-full",
                  active ? "text-zoiko-navy font-semibold" : "text-muted-foreground",
                )}>
                  {step.label}
                </span>
              </div>
              {i < PIPELINE_STEPS.length - 1 && (
                <div className={cn("h-px flex-1 mx-1", done ? "bg-emerald-600" : "bg-border")} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
