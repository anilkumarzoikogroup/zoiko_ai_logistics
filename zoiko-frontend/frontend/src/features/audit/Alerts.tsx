import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { zoikoApi } from "@/api/zoiko";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/utils/cn";
import {
  AlertTriangle, AlertCircle, Info, BellOff, CheckCircle2,
  Clock,
} from "lucide-react";
import type { KafkaEvent } from "@/types";

type Severity = "critical" | "warning" | "info";

interface Alert {
  id: string;
  severity: Severity;
  title: string;
  desc: string;
  time: string;
  source: string;
  snoozed?: boolean;
}

const SEV_CONFIG = {
  critical: { label: "Critical", color: "text-red-700",    bg: "bg-red-50",    border: "border-red-200",    icon: AlertCircle,   dot: "bg-red-500"   },
  warning:  { label: "Warning",  color: "text-amber-700",  bg: "bg-amber-50",  border: "border-amber-200",  icon: AlertTriangle, dot: "bg-amber-500" },
  info:     { label: "Info",     color: "text-blue-700",   bg: "bg-blue-50",   border: "border-blue-200",   icon: Info,          dot: "bg-blue-500"  },
};

function severityForTopic(topic: string): Severity {
  const t = topic.toLowerCase();
  if (t.includes("error") || t.includes("fail") || t.includes("abort") || t.includes("reject")) return "critical";
  if (t.includes("pending") || t.includes("wait") || t.includes("retry") || t.includes("warn")) return "warning";
  return "info";
}

function kafkaEventToAlert(e: KafkaEvent, i: number): Alert {
  const severity = severityForTopic(e.topic);
  const title = e.topic.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
  const key = e.key?.slice(0, 8) ?? "—";
  const desc = `Event on case ${key}. ${Object.entries(e.payload ?? {})
    .slice(0, 3)
    .map(([k, v]) => `${k}: ${JSON.stringify(v)}`)
    .join(" · ")}`;
  const time = new Date(e.published_at).toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: true,
  });
  return { id: `evt_${i}`, severity, title, desc, time, source: "Zoiko Pipeline" };
}

type Tab = "all" | Severity;

function AlertCard({ alert }: { alert: Alert }) {
  const [dismissed, setDismissed] = useState(false);
  if (dismissed) return null;
  const cfg = SEV_CONFIG[alert.severity];
  const Icon = cfg.icon;
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
            <p className="text-xs text-foreground/70 mt-1 leading-relaxed line-clamp-2">{alert.desc}</p>
          </div>
        </div>
        <button onClick={() => setDismissed(true)} className="text-muted-foreground hover:text-foreground flex-shrink-0">
          <CheckCircle2 className="h-4 w-4" />
        </button>
      </div>
      <div className="flex items-center gap-3 text-[10px] text-muted-foreground pl-7">
        <span>{alert.source}</span>
        <span>·</span>
        <Clock className="h-2.5 w-2.5" />
        <span>{alert.time}</span>
      </div>
    </div>
  );
}

export default function Alerts() {
  const [activeTab, setActiveTab] = useState<Tab>("all");

  const { data: kafkaEvents = [], isLoading } = useQuery({
    queryKey: ["kafkaEvents"],
    queryFn: zoikoApi.listKafkaEvents,
    refetchInterval: 30_000,
  });

  const alerts: Alert[] = (kafkaEvents as KafkaEvent[]).map(kafkaEventToAlert);

  const filtered = alerts.filter(a => activeTab === "all" || a.severity === activeTab);

  const criticalCount = alerts.filter(a => a.severity === "critical").length;
  const warningCount  = alerts.filter(a => a.severity === "warning").length;
  const infoCount     = alerts.filter(a => a.severity === "info").length;

  const tabs: { id: Tab; label: string; count: number }[] = [
    { id: "all",      label: "All",      count: alerts.length  },
    { id: "critical", label: "Critical", count: criticalCount  },
    { id: "warning",  label: "Warning",  count: warningCount   },
    { id: "info",     label: "Info",     count: infoCount      },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-zoiko-navy">Alerts &amp; Anomalies</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Real-time events from every pipeline stage — ingestion, validation, governance, execution.
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
        {tabs.map(tab => (
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
        {isLoading ? (
          <Card>
            <CardContent className="flex items-center justify-center py-12 text-muted-foreground gap-3">
              <div className="h-4 w-4 rounded-full border-2 border-zoiko-navy border-t-transparent animate-spin" />
              <p>Loading pipeline events…</p>
            </CardContent>
          </Card>
        ) : filtered.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-12 text-muted-foreground gap-3">
              <CheckCircle2 className="h-10 w-10 text-emerald-400" />
              <p className="font-medium">
                {alerts.length === 0
                  ? "No pipeline events yet — create cases to see activity"
                  : "No alerts in this category"}
              </p>
            </CardContent>
          </Card>
        ) : (
          filtered.map(alert => <AlertCard key={alert.id} alert={alert} />)
        )}
      </div>
    </div>
  );
}
