import { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/utils/cn";
import {
  AlertTriangle, AlertCircle, Info, BellOff, CheckCircle2,
  TrendingUp, ShieldAlert, Clock, Key, Zap, Users,
} from "lucide-react";

type Severity = "critical" | "warning" | "info";

interface Alert {
  id: string;
  severity: Severity;
  title: string;
  desc: string;
  time: string;
  source: string;
  snoozed?: boolean;
  resolved?: boolean;
}

const ALERTS: Alert[] = [
  {
    id: "a1", severity: "critical",
    title: "BlueDart invoice spike detected",
    desc: "Carrier BlueDart submitted 14 invoices in 3 minutes — 8× above baseline. Possible bulk re-submission of previously rejected invoices.",
    time: "2 min ago", source: "Ingestion Service",
  },
  {
    id: "a2", severity: "critical",
    title: "Ed25519 signature verification failed",
    desc: "case_0019: signature does not verify against tenant's current public key. Invoice may have been tampered with post-signing.",
    time: "18 min ago", source: "Canonical Truth",
  },
  {
    id: "a3", severity: "critical",
    title: "SoD violation attempt blocked",
    desc: "user_analyst_03 attempted to approve their own proposal (case_0031). Separation-of-Duties rule enforced — decision rejected.",
    time: "1 hr ago", source: "Governance Service",
  },
  {
    id: "a4", severity: "warning",
    title: "Evidence bundling latency elevated",
    desc: "Stage P95 latency is 1,240ms — 3× normal. Merkle tree computation slowing for bundles with >50 items.",
    time: "3 hr ago", source: "Evidence Service",
  },
  {
    id: "a5", severity: "warning",
    title: "3 governance tokens expired before redemption",
    desc: "Tokens tok_b3c1, tok_d4e2, tok_f5a8 reached 15-min TTL without Phase 4 redemption. Cases returned to APPROVED state.",
    time: "5 hr ago", source: "Token Service",
  },
  {
    id: "a6", severity: "warning",
    title: "Delhivery connector: intermittent 503 errors",
    desc: "Carrier API returning 503 on 12% of credit memo submissions. Auto-retry enabled, 3 cases delayed.",
    time: "6 hr ago", source: "Execution Gateway",
  },
  {
    id: "a7", severity: "warning",
    title: "OPA policy evaluation slow",
    desc: "OPA response time increased to 420ms average. Check OPA server resources if this continues.",
    time: "8 hr ago", source: "API Gateway",
  },
  {
    id: "a8", severity: "warning",
    title: "Contract rate missing for new route",
    desc: "No contract rate found for Vizag→Hyderabad route. 2 invoices auto-rejected with reason: no_contract.",
    time: "10 hr ago", source: "Validation Service",
  },
  {
    id: "a9", severity: "info",
    title: "27 recoveries reconciled successfully",
    desc: "Batch reconciliation completed. ₹2,70,000 recovered across 27 cases. ACR records locked in WORM index.",
    time: "2 hr ago", source: "Reconciliation Service",
  },
  {
    id: "a10", severity: "info",
    title: "Signing key rotation scheduled",
    desc: "Key amazon-india-signing-2025-01 expires in 10 days. New key amazon-india-signing-2025-02 staged and ready.",
    time: "4 hr ago", source: "KMS",
  },
  {
    id: "a11", severity: "info",
    title: "New analyst account created",
    desc: "user_analyst_07 (priya.sharma@amazon.in) added to amazon-india tenant with analyst role.",
    time: "Yesterday", source: "Identity Service",
  },
  {
    id: "a12", severity: "info",
    title: "Phase 3 demo completed successfully",
    desc: "SC-001 end-to-end demo: BlueDart ₹4,500 overcharge detected, proposed, approved, token issued. All 46 tests passed.",
    time: "2 days ago", source: "System",
  },
  {
    id: "s1", severity: "warning",
    title: "High confidence threshold alert (snoozed)",
    desc: "Snoozed until tomorrow.",
    time: "1 day ago", source: "Reasoning Service", snoozed: true,
  },
];

const SEV_CONFIG = {
  critical: { label: "Critical", color: "text-red-700",    bg: "bg-red-50",    border: "border-red-200",    icon: AlertCircle,  dot: "bg-red-500"   },
  warning:  { label: "Warning",  color: "text-amber-700",  bg: "bg-amber-50",  border: "border-amber-200",  icon: AlertTriangle, dot: "bg-amber-500" },
  info:     { label: "Info",     color: "text-blue-700",   bg: "bg-blue-50",   border: "border-blue-200",   icon: Info,          dot: "bg-blue-500"  },
};

const SOURCE_ICONS: Record<string, React.ElementType> = {
  "Ingestion Service": TrendingUp,
  "Canonical Truth":   ShieldAlert,
  "Governance Service":Users,
  "Evidence Service":  Clock,
  "Token Service":     Key,
  "Execution Gateway": Zap,
  "KMS":               Key,
  "API Gateway":       ShieldAlert,
};

type Tab = "all" | Severity | "snoozed";

const TABS: { id: Tab; label: string; count: number }[] = [
  { id: "all",      label: "All",      count: ALERTS.filter(a => !a.snoozed).length },
  { id: "critical", label: "Critical", count: ALERTS.filter(a => a.severity === "critical" && !a.snoozed).length },
  { id: "warning",  label: "Warning",  count: ALERTS.filter(a => a.severity === "warning" && !a.snoozed).length },
  { id: "info",     label: "Info",     count: ALERTS.filter(a => a.severity === "info" && !a.snoozed).length },
  { id: "snoozed",  label: "Snoozed",  count: ALERTS.filter(a => a.snoozed).length },
];

function AlertCard({ alert }: { alert: Alert }) {
  const [dismissed, setDismissed] = useState(false);
  if (dismissed) return null;
  const cfg = SEV_CONFIG[alert.severity];
  const Icon = cfg.icon;
  const SourceIcon = SOURCE_ICONS[alert.source] ?? Info;
  return (
    <div className={cn("rounded-xl border p-4 space-y-2", cfg.bg, cfg.border)}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2.5 flex-1 min-w-0">
          <Icon className={cn("h-4 w-4 flex-shrink-0 mt-0.5", cfg.color)} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <p className={cn("font-semibold text-sm", cfg.color)}>{alert.title}</p>
              <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded-full border", cfg.bg, cfg.border, cfg.color)}>
                {cfg.label.toUpperCase()}
              </span>
            </div>
            <p className="text-xs text-foreground/70 mt-1 leading-relaxed">{alert.desc}</p>
          </div>
        </div>
        <button onClick={() => setDismissed(true)} className="text-muted-foreground hover:text-foreground flex-shrink-0">
          <CheckCircle2 className="h-4 w-4" />
        </button>
      </div>
      <div className="flex items-center gap-3 text-[10px] text-muted-foreground pl-7">
        <SourceIcon className="h-3 w-3" />
        <span>{alert.source}</span>
        <span>·</span>
        <Clock className="h-2.5 w-2.5" />
        <span>{alert.time}</span>
        {alert.snoozed && (
          <><span>·</span><BellOff className="h-2.5 w-2.5" /><span>Snoozed</span></>
        )}
      </div>
    </div>
  );
}

export default function Alerts() {
  const [activeTab, setActiveTab] = useState<Tab>("all");

  const filtered = ALERTS.filter(a => {
    if (activeTab === "all")     return !a.snoozed;
    if (activeTab === "snoozed") return !!a.snoozed;
    return a.severity === activeTab && !a.snoozed;
  });

  const criticalCount = ALERTS.filter(a => a.severity === "critical" && !a.snoozed).length;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-zoiko-navy">Alerts &amp; Anomalies</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Real-time alerts from every pipeline stage — ingestion, validation, governance, execution.
          </p>
        </div>
        {criticalCount > 0 && (
          <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-red-50 border border-red-200 text-red-700">
            <span className="h-2 w-2 rounded-full bg-red-500 animate-pulse" />
            <span className="text-sm font-bold">{criticalCount} critical alert{criticalCount > 1 ? "s" : ""}</span>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b">
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              "flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px",
              activeTab === tab.id
                ? "border-zoiko-navy text-zoiko-navy"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            {tab.label}
            <span className={cn(
              "text-[10px] font-bold px-1.5 py-0.5 rounded-full min-w-[18px] text-center",
              activeTab === tab.id
                ? "bg-zoiko-navy text-white"
                : tab.id === "critical" && tab.count > 0
                  ? "bg-red-100 text-red-700"
                  : "bg-secondary text-muted-foreground"
            )}>
              {tab.count}
            </span>
          </button>
        ))}
      </div>

      {/* Alert list */}
      <div className="space-y-3">
        {filtered.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-12 text-muted-foreground gap-3">
              <CheckCircle2 className="h-10 w-10 text-emerald-400" />
              <p className="font-medium">No alerts in this category</p>
            </CardContent>
          </Card>
        ) : (
          filtered.map(alert => <AlertCard key={alert.id} alert={alert} />)
        )}
      </div>
    </div>
  );
}
