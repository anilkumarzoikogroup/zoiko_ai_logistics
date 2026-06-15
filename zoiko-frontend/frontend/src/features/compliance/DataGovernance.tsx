import { useQuery } from "@tanstack/react-query";
import { zoikoApi } from "@/api/zoiko";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/utils/cn";
import {
  Activity, AlertTriangle, AlertCircle, ShieldCheck,
  Archive, Lock, HardDrive, RefreshCw, Trash2, Clock,
} from "lucide-react";
import type { ObservabilityAlert } from "@/types";

const SEV: Record<string, { bg: string; border: string; text: string; icon: React.ElementType }> = {
  CRITICAL: { bg: "bg-red-50",    border: "border-red-200",    text: "text-red-700",    icon: AlertCircle   },
  HIGH:     { bg: "bg-amber-50",  border: "border-amber-200",  text: "text-amber-700",  icon: AlertTriangle },
  MEDIUM:   { bg: "bg-yellow-50", border: "border-yellow-200", text: "text-yellow-700", icon: AlertTriangle },
  LOW:      { bg: "bg-blue-50",   border: "border-blue-200",   text: "text-blue-700",   icon: Activity      },
};

function AlertCard({ a }: { a: ObservabilityAlert }) {
  const cfg = SEV[a.severity] ?? SEV.LOW;
  const Icon = cfg.icon;
  return (
    <div className={cn("rounded-xl border p-4", cfg.bg, cfg.border)}>
      <div className="flex items-start gap-3">
        <Icon className={cn("h-4 w-4 mt-0.5 flex-shrink-0", cfg.text)} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className={cn("font-semibold text-sm", cfg.text)}>{a.alert.replace(/_/g, " ")}</p>
            <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded-full border", cfg.bg, cfg.border, cfg.text)}>
              {a.severity}
            </span>
            <span className="text-xs text-slate-500">count: {a.count}</span>
          </div>
          <p className="text-xs text-slate-600 mt-1 leading-relaxed">{a.detail}</p>
        </div>
      </div>
    </div>
  );
}

function MetricTile({ label, value, icon: Icon, color }: { label: string; value: string | number; icon: React.ElementType; color: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 flex items-center gap-3">
      <div className={cn("h-9 w-9 rounded-lg flex items-center justify-center flex-shrink-0", color)}>
        <Icon className="h-4 w-4 text-white" />
      </div>
      <div className="min-w-0">
        <p className="text-[11px] text-slate-500 truncate">{label}</p>
        <p className="text-lg font-bold text-slate-800 leading-tight">{value}</p>
      </div>
    </div>
  );
}

export default function DataGovernance() {
  const { data: metrics, isLoading: mLoad, error: mErr } = useQuery({
    queryKey: ["obs-metrics"],
    queryFn: () => zoikoApi.getObservabilityMetrics(),
    retry: 1,
  });

  const { data: alerts = [], isLoading: aLoad } = useQuery({
    queryKey: ["obs-alerts"],
    queryFn: () => zoikoApi.getObservabilityAlerts(),
    retry: 1,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-slate-800">Data Governance Dashboard</h1>
        <p className="text-sm text-slate-500 mt-0.5">C07 §19 — Live observability metrics and active alert conditions</p>
      </div>

      {/* Active Alerts */}
      <Card>
        <CardContent className="p-5">
          <div className="flex items-center gap-2 mb-4">
            <AlertCircle className="h-4 w-4 text-red-500" />
            <h2 className="font-semibold text-slate-700 text-sm">Active Alert Conditions</h2>
            {alerts.length > 0 && (
              <span className="ml-auto text-[10px] font-bold bg-red-100 text-red-600 px-2 py-0.5 rounded-full">
                {alerts.length} FIRING
              </span>
            )}
          </div>
          {aLoad && <p className="text-sm text-slate-400">Loading…</p>}
          {!aLoad && alerts.length === 0 && (
            <div className="flex items-center gap-2 text-emerald-600">
              <ShieldCheck className="h-4 w-4" />
              <p className="text-sm font-medium">All clear — no alert conditions firing</p>
            </div>
          )}
          <div className="space-y-3">
            {alerts.map((a, i) => <AlertCard key={i} a={a} />)}
          </div>
        </CardContent>
      </Card>

      {/* Metric tiles */}
      {mLoad && <p className="text-sm text-slate-400">Loading metrics…</p>}
      {mErr && (
        <p className="text-sm text-amber-600 bg-amber-50 border border-amber-200 rounded-lg px-4 py-2">
          Could not load metrics — backend may be offline.
        </p>
      )}
      {metrics && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <MetricTile label="Records approaching expiry" value={metrics.records_approaching_expiry} icon={Clock} color="bg-amber-500" />
            <MetricTile label="Blocked by legal hold" value={metrics.records_blocked_by_legal_hold} icon={Lock} color="bg-red-500" />
            <MetricTile label="Residency violations" value={metrics.residency_violations_detected} icon={AlertTriangle} color="bg-rose-500" />
            <MetricTile label="Payload access events" value={metrics.payload_access_events} icon={Activity} color="bg-blue-500" />
            <MetricTile label="Restore verification failures" value={metrics.restore_verification_failures} icon={RefreshCw} color="bg-orange-500" />
            <MetricTile label="Evidence chain failures" value={metrics.evidence_chain_verification_failures} icon={AlertCircle} color="bg-red-600" />
            <MetricTile label="ACR verify failures (restore)" value={metrics.acr_verification_failures_after_restore} icon={Archive} color="bg-purple-500" />
            <MetricTile label="Cross-region access attempts" value={metrics.cross_region_access_attempts} icon={HardDrive} color="bg-slate-500" />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Records by retention class */}
            <Card>
              <CardContent className="p-4">
                <p className="text-xs font-semibold text-slate-500 mb-3 uppercase tracking-wide">Records by Retention Class</p>
                {Object.entries(metrics.records_by_retention_class).length === 0
                  ? <p className="text-xs text-slate-400">No data</p>
                  : Object.entries(metrics.records_by_retention_class).map(([cls, cnt]) => (
                    <div key={cls} className="flex items-center justify-between py-1 border-b border-slate-100 last:border-0">
                      <span className="text-xs text-slate-600">{cls}</span>
                      <span className="text-xs font-bold text-slate-800">{cnt}</span>
                    </div>
                  ))
                }
              </CardContent>
            </Card>

            {/* Archive jobs */}
            <Card>
              <CardContent className="p-4">
                <p className="text-xs font-semibold text-slate-500 mb-3 uppercase tracking-wide">Archive Jobs by Status</p>
                {Object.entries(metrics.archive_jobs).length === 0
                  ? <p className="text-xs text-slate-400">No archive jobs</p>
                  : Object.entries(metrics.archive_jobs).map(([s, cnt]) => (
                    <div key={s} className="flex items-center justify-between py-1 border-b border-slate-100 last:border-0">
                      <span className="text-xs text-slate-600">{s}</span>
                      <span className="text-xs font-bold text-slate-800">{cnt}</span>
                    </div>
                  ))
                }
              </CardContent>
            </Card>

            {/* Legal holds by scope */}
            <Card>
              <CardContent className="p-4">
                <p className="text-xs font-semibold text-slate-500 mb-3 uppercase tracking-wide">Active Legal Holds by Scope</p>
                {Object.entries(metrics.legal_hold_active_by_scope).length === 0
                  ? <p className="text-xs text-slate-400">No active legal holds</p>
                  : Object.entries(metrics.legal_hold_active_by_scope).map(([scope, cnt]) => (
                    <div key={scope} className="flex items-center justify-between py-1 border-b border-slate-100 last:border-0">
                      <span className="text-xs text-slate-600">{scope}</span>
                      <span className="text-xs font-bold text-slate-800">{cnt}</span>
                    </div>
                  ))
                }
              </CardContent>
            </Card>
          </div>

          <div className="text-[11px] text-slate-400 flex items-center gap-1">
            <Clock className="h-3 w-3" />
            Computed at {new Date(metrics.computed_at).toLocaleString()}
          </div>
        </div>
      )}

      {/* Crypto-shred / purge summaries */}
      {metrics && (Object.keys(metrics.crypto_shred_requests).length > 0 || Object.keys(metrics.purge_jobs).length > 0) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-2 mb-3">
                <Trash2 className="h-3.5 w-3.5 text-slate-500" />
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Crypto-Shred Requests</p>
              </div>
              {Object.entries(metrics.crypto_shred_requests).map(([s, cnt]) => (
                <div key={s} className="flex items-center justify-between py-1 border-b border-slate-100 last:border-0">
                  <span className="text-xs text-slate-600">{s}</span>
                  <span className="text-xs font-bold text-slate-800">{cnt}</span>
                </div>
              ))}
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-2 mb-3">
                <Trash2 className="h-3.5 w-3.5 text-slate-500" />
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Purge Jobs</p>
              </div>
              {Object.entries(metrics.purge_jobs).map(([s, cnt]) => (
                <div key={s} className="flex items-center justify-between py-1 border-b border-slate-100 last:border-0">
                  <span className="text-xs text-slate-600">{s}</span>
                  <span className="text-xs font-bold text-slate-800">{cnt}</span>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
