import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { cn, formatDate } from "@/utils/cn";
import { useToast } from "@/hooks/useToast";
import {
  Plus, RefreshCw, Trash2, ChevronDown, ChevronUp,
  CheckCircle2, AlertTriangle, Clock, Copy, Zap, Settings,
  Globe, Mail, Server, Webhook, FileSpreadsheet, Truck,
  Activity, ArrowRight, Info,
} from "lucide-react";

// ── Types ─────────────────────────────────────────────────────────────────────
interface Connector {
  id: string;
  name: string;
  connector_type: string;
  auth_method: string;
  trust_tier: string;
  certification_state: string;
  operational_state: string;
  endpoint_url: string;
  rate_limit_rps: number;
  source_type: string;
  created_at: string;
}

interface IngestionRun {
  id: string;
  connector_id: string;
  status: string;
  records_received: number;
  records_accepted: number;
  records_rejected: number;
  started_at: string;
  completed_at: string | null;
  error_detail: string | null;
}

// ── Config maps ───────────────────────────────────────────────────────────────
const CONNECTOR_TYPES: { type: string; icon: React.ElementType; desc: string; example: string }[] = [
  { type: "API",     icon: Globe,          desc: "REST or SOAP endpoint",      example: "BlueDart API, Delhivery API"  },
  { type: "Webhook", icon: Webhook,        desc: "Carrier pushes to Zoiko",    example: "FedEx events, DHL push"      },
  { type: "Email",   icon: Mail,           desc: "Invoice email parsing",      example: "invoices@carrier.com"        },
  { type: "SFTP",    icon: Server,         desc: "Scheduled file pickup",      example: "carrier SFTP server"         },
  { type: "EDI",     icon: FileSpreadsheet,desc: "Electronic data interchange",example: "X12 810 / EDIFACT"           },
  { type: "Batch",   icon: Truck,          desc: "Bulk file upload",           example: "Monthly invoice batch"       },
  { type: "Portal",  icon: Globe,          desc: "Carrier web portal scraper", example: "DTDC portal"                 },
];

const AUTH_METHODS = ["API_KEY", "OAuth2", "mTLS", "SFTP_KEY", "WEBHOOK_HMAC"];
const TRUST_TIERS  = [
  { tier: "T1", label: "T1 — Fully Certified",   color: "text-emerald-700 bg-emerald-50" },
  { tier: "T2", label: "T2 — Validated",          color: "text-blue-700 bg-blue-50"      },
  { tier: "T3", label: "T3 — Sandbox Tested",     color: "text-indigo-700 bg-indigo-50"  },
  { tier: "T4", label: "T4 — Draft / Untrusted",  color: "text-slate-600 bg-slate-100"   },
];

const OPS_STATES: { state: string; label: string; color: string; dot: string }[] = [
  { state: "healthy",   label: "Healthy",   color: "text-emerald-700 bg-emerald-50 border-emerald-200", dot: "bg-emerald-500" },
  { state: "degraded",  label: "Degraded",  color: "text-amber-700 bg-amber-50 border-amber-200",       dot: "bg-amber-500"   },
  { state: "frozen",    label: "Frozen",    color: "text-red-700 bg-red-50 border-red-200",             dot: "bg-red-500"     },
  { state: "suspended", label: "Suspended", color: "text-red-700 bg-red-50 border-red-200",             dot: "bg-red-500"     },
];

const CERT_STATES: { state: string; color: string }[] = [
  { state: "Active",           color: "text-emerald-700 bg-emerald-50"   },
  { state: "Certified",        color: "text-blue-700 bg-blue-50"         },
  { state: "SandboxValidated", color: "text-indigo-700 bg-indigo-50"     },
  { state: "Registered",       color: "text-slate-700 bg-slate-100"      },
  { state: "Draft",            color: "text-slate-500 bg-slate-50"       },
  { state: "Suspended",        color: "text-red-700 bg-red-50"           },
  { state: "Deprecated",       color: "text-orange-700 bg-orange-50"     },
];

const RUN_STATUS_STYLE: Record<string, { dot: string; text: string }> = {
  completed: { dot: "bg-emerald-500", text: "text-emerald-700" },
  running:   { dot: "bg-blue-500 animate-pulse", text: "text-blue-700" },
  failed:    { dot: "bg-red-500", text: "text-red-700"     },
  queued:    { dot: "bg-slate-400", text: "text-slate-600" },
};

// ── Small components ──────────────────────────────────────────────────────────
function OpsBadge({ state }: { state: string }) {
  const s = OPS_STATES.find(o => o.state === state);
  if (!s) return <span className="text-[10px] font-semibold text-slate-500 bg-slate-100 border border-slate-200 px-2 py-0.5 rounded-full">{state}</span>;
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-[10px] font-bold px-2 py-0.5 rounded-full border", s.color)}>
      <span className={cn("h-1.5 w-1.5 rounded-full", s.dot)} />
      {s.label}
    </span>
  );
}

function CertBadge({ state }: { state: string }) {
  const s = CERT_STATES.find(c => c.state === state);
  if (!s) return <span className="text-[10px] font-semibold text-slate-500 bg-slate-100 px-2 py-0.5 rounded">{state}</span>;
  return (
    <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded", s.color)}>{state}</span>
  );
}

// ── Connector Card ────────────────────────────────────────────────────────────
function ConnectorCard({ connector, onDelete, onSync, onStateChange }: {
  connector: Connector;
  onDelete: () => void;
  onSync: () => void;
  onStateChange: (ops?: string, cert?: string) => void;
}) {
  const toast = useToast();
  const [expanded, setExpanded]       = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [newOps,  setNewOps]          = useState(connector.operational_state);
  const [newCert, setNewCert]         = useState(connector.certification_state);

  const typeInfo = CONNECTOR_TYPES.find(t => t.type === connector.connector_type) ?? CONNECTOR_TYPES[0];
  const TypeIcon = typeInfo.icon;
  const isWebhook = connector.connector_type === "Webhook" || connector.auth_method === "WEBHOOK_HMAC";
  const webhookUrl = `${window.location.origin}/api/v1/webhooks/ingest/${connector.source_type}`;

  const { data: runs = [] } = useQuery<IngestionRun[]>({
    queryKey: ["ingestion-runs", connector.id],
    queryFn:  async () => {
      const { data } = await api.get(`/ingestion/runs?connector_id=${connector.id}`);
      return data;
    },
    enabled: expanded,
    refetchInterval: expanded ? 10000 : false,
  });

  function copyWebhookUrl() {
    navigator.clipboard.writeText(webhookUrl).then(
      () => toast.success("Copied", "Webhook URL copied to clipboard"),
      () => toast.error("Copy failed", "")
    );
  }

  const lastRun = runs[0];

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">

      {/* Main row */}
      <div className="flex items-center gap-4 px-5 py-4">

        {/* Type icon */}
        <div className="h-10 w-10 rounded-xl bg-blue-50 flex items-center justify-center flex-shrink-0">
          <TypeIcon className="h-5 w-5 text-blue-600" />
        </div>

        {/* Name + meta */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-[14px] font-bold text-slate-800">{connector.name}</p>
            <span className="text-[10px] text-slate-500 bg-slate-100 px-2 py-0.5 rounded font-semibold">{connector.connector_type}</span>
            <span className="text-[10px] text-slate-400 bg-slate-50 px-2 py-0.5 rounded">{connector.auth_method}</span>
            {isWebhook && (
              <span className="text-[10px] text-blue-500 bg-blue-50 px-2 py-0.5 rounded font-mono">/{connector.source_type}</span>
            )}
            <CertBadge state={connector.certification_state} />
          </div>
          <div className="flex items-center gap-3 mt-1 flex-wrap">
            {connector.endpoint_url && (
              <span className="text-[11px] text-slate-400 font-mono truncate max-w-[240px]">{connector.endpoint_url}</span>
            )}
            <span className="text-[11px] text-slate-400">Tier {connector.trust_tier}</span>
            <span className="text-[11px] text-slate-400">{connector.rate_limit_rps} rps</span>
            {lastRun && (
              <span className="text-[11px] text-slate-400">
                Last run: {formatDate(lastRun.started_at)} ·{" "}
                <span className={cn("font-semibold", RUN_STATUS_STYLE[lastRun.status]?.text ?? "text-slate-500")}>
                  {lastRun.status}
                </span>
              </span>
            )}
          </div>
        </div>

        {/* Ops status */}
        <OpsBadge state={connector.operational_state} />

        {/* Actions */}
        <div className="flex items-center gap-1 flex-shrink-0">
          <button
            onClick={onSync}
            title={connector.operational_state === "healthy" ? "Trigger sync" : "Connector must be healthy to sync"}
            className={cn(
              "p-2 rounded-lg transition-colors",
              connector.operational_state === "healthy"
                ? "text-slate-400 hover:text-blue-600 hover:bg-blue-50"
                : "text-slate-200 cursor-not-allowed"
            )}
          >
            <Zap className="h-4 w-4" />
          </button>
          <button
            onClick={() => setShowSettings(v => !v)}
            title="Configure"
            className={cn("p-2 rounded-lg transition-colors", showSettings ? "bg-slate-100 text-slate-700" : "text-slate-400 hover:text-slate-600 hover:bg-slate-50")}
          >
            <Settings className="h-4 w-4" />
          </button>
          <button
            onClick={() => setExpanded(v => !v)}
            title="View runs"
            className="p-2 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-50 transition-colors"
          >
            {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </button>
          <button
            onClick={() => { if (confirm(`Delete connector "${connector.name}"? This cannot be undone.`)) onDelete(); }}
            title="Delete connector"
            className="p-2 rounded-lg text-slate-300 hover:text-red-500 hover:bg-red-50 transition-colors"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Settings panel */}
      {showSettings && (
        <div className="border-t border-slate-100 px-5 py-4 bg-slate-50 space-y-4">
          <p className="text-[12px] font-bold text-slate-600 uppercase tracking-wider">Connector Settings</p>

          {/* Webhook URL */}
          {isWebhook && (
            <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 space-y-1.5">
              <div className="flex items-center gap-1.5">
                <Info className="h-3.5 w-3.5 text-blue-500" />
                <p className="text-[11px] font-bold text-blue-700">Inbound Webhook URL</p>
              </div>
              <p className="text-[10px] text-blue-600">Give this URL to your carrier. They POST invoices here — Zoiko verifies the HMAC signature and ingests automatically.</p>
              <div className="flex items-center gap-2 mt-2">
                <code className="flex-1 text-[10px] font-mono bg-white border border-blue-200 rounded px-2 py-1.5 text-slate-700 truncate">
                  {webhookUrl}
                </code>
                <button
                  onClick={copyWebhookUrl}
                  className="flex items-center gap-1 px-2.5 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded text-[10px] font-bold flex-shrink-0 transition-colors"
                >
                  <Copy className="h-3 w-3" /> Copy
                </button>
              </div>
            </div>
          )}

          {/* State controls */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-[11px] font-semibold text-slate-500 mb-1.5">Operational State</label>
              <select
                value={newOps}
                onChange={e => setNewOps(e.target.value)}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-[12px] focus:outline-none focus:ring-2 focus:ring-blue-500/30"
              >
                {OPS_STATES.map(s => (
                  <option key={s.state} value={s.state}>{s.label}</option>
                ))}
              </select>
              <p className="text-[10px] text-slate-400 mt-1">Only <strong>healthy</strong> connectors can be synced.</p>
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-slate-500 mb-1.5">Certification State</label>
              <select
                value={newCert}
                onChange={e => setNewCert(e.target.value)}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-[12px] focus:outline-none focus:ring-2 focus:ring-blue-500/30"
              >
                {CERT_STATES.map(s => (
                  <option key={s.state} value={s.state}>{s.state}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="flex items-center gap-2 pt-1">
            <button
              onClick={() => { onStateChange(newOps, newCert); setShowSettings(false); }}
              className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-[12px] font-bold transition-colors"
            >
              <CheckCircle2 className="h-3.5 w-3.5" /> Save Changes
            </button>
            <button onClick={() => setShowSettings(false)} className="px-4 py-2 text-[12px] text-slate-500 hover:text-slate-700 transition-colors">Cancel</button>
          </div>
        </div>
      )}

      {/* Ingestion runs panel */}
      {expanded && (
        <div className="border-t border-slate-100 px-5 py-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-slate-400" />
              <p className="text-[12px] font-bold text-slate-600">Ingestion Runs</p>
            </div>
            <button
              onClick={onSync}
              disabled={connector.operational_state !== "healthy"}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg text-[11px] font-bold transition-colors"
            >
              <Zap className="h-3 w-3" /> Trigger Sync
            </button>
          </div>

          {runs.length === 0 ? (
            <div className="py-8 text-center">
              <RefreshCw className="h-7 w-7 text-slate-200 mx-auto mb-2" />
              <p className="text-[12px] text-slate-400">No ingestion runs yet.</p>
              {connector.operational_state === "healthy"
                ? <p className="text-[11px] text-slate-400 mt-1">Click <strong>Trigger Sync</strong> to start your first run.</p>
                : <p className="text-[11px] text-slate-400 mt-1">Set operational state to <strong>Healthy</strong> first.</p>
              }
            </div>
          ) : (
            <div className="space-y-2">
              {runs.slice(0, 10).map((run: IngestionRun) => {
                const style = RUN_STATUS_STYLE[run.status] ?? { dot: "bg-slate-400", text: "text-slate-600" };
                return (
                  <div key={run.id} className="flex items-center gap-3 py-2 border-b border-slate-50 last:border-0">
                    <span className={cn("h-2 w-2 rounded-full flex-shrink-0 mt-0.5", style.dot)} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-3 flex-wrap">
                        <span className={cn("text-[11px] font-bold", style.text)}>{run.status.toUpperCase()}</span>
                        <span className="text-[10px] text-slate-400">{formatDate(run.started_at)}</span>
                        {run.completed_at && (
                          <span className="text-[10px] text-slate-400">→ {formatDate(run.completed_at)}</span>
                        )}
                      </div>
                      <div className="flex items-center gap-4 mt-0.5">
                        <span className="text-[10px] text-slate-500">
                          Received <strong className="text-slate-700">{run.records_received ?? 0}</strong>
                        </span>
                        <span className="text-[10px] text-emerald-600">
                          Accepted <strong>{run.records_accepted ?? 0}</strong>
                        </span>
                        {(run.records_rejected ?? 0) > 0 && (
                          <span className="text-[10px] text-red-600">
                            Rejected <strong>{run.records_rejected}</strong>
                          </span>
                        )}
                      </div>
                      {run.error_detail && (
                        <p className="text-[10px] text-red-500 mt-0.5 font-mono truncate">{run.error_detail}</p>
                      )}
                    </div>
                    <code className="text-[9px] font-mono text-slate-300 flex-shrink-0">{run.id.slice(0, 8)}</code>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── New Connector Form ────────────────────────────────────────────────────────
const BLANK_FORM = { name: "", connector_type: "API", auth_method: "API_KEY", trust_tier: "T2", endpoint_url: "", rate_limit_rps: 10, source_type: "" };

function slugify(name: string): string {
  return name.replace(/[^a-zA-Z0-9]+/g, "-").replace(/^-+|-+$/g, "").toLowerCase();
}

function NewConnectorForm({ onClose, onCreate }: {
  onClose: () => void;
  onCreate: (form: typeof BLANK_FORM) => void;
}) {
  const [form, setForm] = useState(BLANK_FORM);
  const [step, setStep] = useState<"type" | "details">("type");

  const typeInfo = CONNECTOR_TYPES.find(t => t.type === form.connector_type) ?? CONNECTOR_TYPES[0];

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
        <div>
          <p className="text-[14px] font-bold text-slate-800">Add Connector</p>
          <p className="text-[11px] text-slate-400 mt-0.5">Connect a carrier system to ingest invoices automatically.</p>
        </div>
        <button onClick={onClose} className="text-slate-300 hover:text-slate-500 text-[11px] transition-colors">✕ Cancel</button>
      </div>

      {/* Step 1: Pick type */}
      {step === "type" && (
        <div className="p-5 space-y-4">
          <p className="text-[12px] font-bold text-slate-500 uppercase tracking-wider">Step 1 — Choose connection type</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {CONNECTOR_TYPES.map(t => {
              const Icon = t.icon;
              const selected = form.connector_type === t.type;
              return (
                <button
                  key={t.type}
                  onClick={() => setForm(f => ({ ...f, connector_type: t.type }))}
                  className={cn(
                    "flex flex-col items-center gap-2 p-3 rounded-xl border-2 text-center transition-all",
                    selected ? "border-blue-500 bg-blue-50" : "border-slate-200 hover:border-slate-300 bg-white"
                  )}
                >
                  <Icon className={cn("h-6 w-6", selected ? "text-blue-600" : "text-slate-400")} />
                  <span className={cn("text-[12px] font-bold", selected ? "text-blue-700" : "text-slate-600")}>{t.type}</span>
                  <span className={cn("text-[10px] leading-tight", selected ? "text-blue-600" : "text-slate-400")}>{t.desc}</span>
                </button>
              );
            })}
          </div>
          <div className="rounded-lg bg-slate-50 border border-slate-200 px-4 py-3">
            <p className="text-[11px] font-semibold text-slate-600">{typeInfo.type} — {typeInfo.desc}</p>
            <p className="text-[10px] text-slate-400 mt-0.5">Examples: {typeInfo.example}</p>
          </div>
          <div className="flex justify-end">
            <button
              onClick={() => setStep("details")}
              className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-[13px] font-bold transition-colors"
            >
              Next <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {/* Step 2: Details */}
      {step === "details" && (
        <div className="p-5 space-y-4">
          <div className="flex items-center gap-2">
            <button onClick={() => setStep("type")} className="text-[11px] text-blue-600 hover:underline">← Back</button>
            <p className="text-[12px] font-bold text-slate-500 uppercase tracking-wider">Step 2 — Configure {form.connector_type} connector</p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <label className="block text-[11px] font-semibold text-slate-600 mb-1.5">Connector Name *</label>
              <input
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-[13px] focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                placeholder={`e.g. BlueDart ${form.connector_type} Integration`}
                value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              />
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-slate-600 mb-1.5">Auth Method</label>
              <select
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-[13px] focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                value={form.auth_method}
                onChange={e => setForm(f => ({ ...f, auth_method: e.target.value }))}
              >
                {AUTH_METHODS.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-slate-600 mb-1.5">Trust Tier</label>
              <select
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-[13px] focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                value={form.trust_tier}
                onChange={e => setForm(f => ({ ...f, trust_tier: e.target.value }))}
              >
                {TRUST_TIERS.map(t => <option key={t.tier} value={t.tier}>{t.label}</option>)}
              </select>
            </div>
            <div className="col-span-2">
              <label className="block text-[11px] font-semibold text-slate-600 mb-1.5">
                Endpoint URL {["API","SFTP"].includes(form.connector_type) && "*"}
              </label>
              <input
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-[13px] font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                placeholder={form.connector_type === "SFTP" ? "sftp://carrier-host:22/invoices/" : "https://api.carrier.com/v1/invoices"}
                value={form.endpoint_url}
                onChange={e => setForm(f => ({ ...f, endpoint_url: e.target.value }))}
              />
            </div>
          </div>

          {form.connector_type === "Webhook" && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 space-y-2">
              <p className="text-[11px] font-bold text-amber-700 flex items-center gap-1.5">
                <Info className="h-3.5 w-3.5" /> Webhook setup
              </p>
              <p className="text-[11px] text-amber-700">
                After creating this connector, you'll get a <strong>webhook URL</strong> to give your carrier.
                They POST invoice payloads to it — Zoiko verifies HMAC signatures and ingests automatically.
              </p>
              <div>
                <label className="block text-[11px] font-semibold text-amber-700 mb-1">URL slug (must be unique)</label>
                <input
                  className="w-full border border-amber-200 rounded-lg px-3 py-2 text-[12px] font-mono focus:outline-none focus:ring-2 focus:ring-amber-400/40"
                  placeholder={form.name ? slugify(form.name) : "e.g. fedex, dhl-india"}
                  value={form.source_type}
                  onChange={e => setForm(f => ({ ...f, source_type: e.target.value }))}
                />
                <p className="text-[10px] text-amber-600 mt-1 font-mono">
                  {window.location.origin}/api/v1/webhooks/ingest/{form.source_type || (form.name ? slugify(form.name) : "...")}
                </p>
              </div>
            </div>
          )}

          <div className="flex items-center gap-3 pt-2">
            <button
              onClick={() => onCreate(form)}
              disabled={!form.name.trim()}
              className="flex items-center gap-1.5 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white rounded-lg text-[13px] font-bold transition-colors"
            >
              <Plus className="h-4 w-4" /> Create Connector
            </button>
            <p className="text-[11px] text-slate-400">
              After creation, set <strong>Operational State → Healthy</strong> to enable syncing.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function ConnectorsPage() {
  const qc    = useQueryClient();
  const toast = useToast();
  const [showForm, setShowForm] = useState(false);

  const { data: connectors = [], isLoading } = useQuery<Connector[]>({
    queryKey: ["connectors"],
    queryFn:  async () => { const { data } = await api.get("/connectors"); return data; },
    refetchInterval: 15000,
  });

  const createMut = useMutation({
    mutationFn: async (body: typeof BLANK_FORM) => {
      const { data } = await api.post("/connectors", body, { headers: { "Idempotency-Key": crypto.randomUUID() } });
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["connectors"] });
      setShowForm(false);
      toast.success("Connector created", "Open settings to set it Healthy and trigger your first sync.");
    },
    onError: (e: unknown) => {
      const msg = (e as any)?.response?.data?.detail;
      toast.error("Create failed", typeof msg === "string" ? msg : "Check backend is running.");
    },
  });

  const stateMut = useMutation({
    mutationFn: async ({ id, ops, cert }: { id: string; ops?: string; cert?: string }) => {
      await api.patch(`/connectors/${id}/state`, { operational_state: ops, certification_state: cert }, {
        headers: { "Idempotency-Key": crypto.randomUUID() },
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["connectors"] });
      toast.success("State updated", "");
    },
    onError: (e: unknown) => {
      const msg = (e as any)?.response?.data?.detail;
      toast.error("Update failed", typeof msg === "string" ? msg : "Could not update connector state.");
    },
  });

  const syncMut = useMutation({
    mutationFn: async (id: string) => {
      const { data } = await api.post(`/ingestion/connectors/${id}/sync`, {}, { headers: { "Idempotency-Key": crypto.randomUUID() } });
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["connectors"] });
      toast.success("Sync triggered", "Ingestion run started — check the run history below.");
    },
    onError: (e: unknown) => {
      const msg = (e as any)?.response?.data?.detail;
      toast.error("Sync failed", typeof msg === "string" ? msg : "Connector must be Healthy to sync.");
    },
  });

  const deleteMut = useMutation({
    mutationFn: async (id: string) => { await api.delete(`/connectors/${id}`); },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["connectors"] }); toast.success("Connector deleted", ""); },
    onError: () => toast.error("Delete failed", ""),
  });

  const healthy   = connectors.filter(c => c.operational_state === "healthy").length;
  const degraded  = connectors.filter(c => c.operational_state === "degraded").length;
  const suspended = connectors.filter(c => ["frozen", "suspended"].includes(c.operational_state)).length;

  return (
    <div className="space-y-5">

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-[20px] font-extrabold text-slate-800">Connectors</h1>
          <p className="text-[13px] text-slate-500 mt-0.5">
            Connect your carriers' systems — invoices flow in automatically, overcharges detected instantly.
          </p>
        </div>
        <button
          onClick={() => setShowForm(v => !v)}
          className="flex items-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-[13px] font-bold transition-colors shadow-sm flex-shrink-0"
        >
          <Plus className="h-4 w-4" /> Add Connector
        </button>
      </div>

      {/* Summary tiles */}
      {connectors.length > 0 && (
        <div className="grid grid-cols-3 gap-3">
          {[
            { label: "Active Connectors",  value: healthy,   accent: "#10b981", icon: CheckCircle2 },
            { label: "Degraded",           value: degraded,  accent: "#f59e0b", icon: AlertTriangle },
            { label: "Suspended/Frozen",   value: suspended, accent: "#ef4444", icon: Clock        },
          ].map(t => (
            <div key={t.label} className="bg-white rounded-xl border border-slate-200 px-4 py-3 flex items-center gap-3 shadow-sm">
              <div className="h-9 w-9 rounded-lg flex items-center justify-center flex-shrink-0" style={{ background: t.accent + "15" }}>
                <t.icon className="h-4 w-4" style={{ color: t.accent }} />
              </div>
              <div>
                <p className="text-[20px] font-extrabold text-slate-800 leading-tight">{t.value}</p>
                <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide">{t.label}</p>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* How it works — shown when empty */}
      {connectors.length === 0 && !showForm && (
        <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
          <p className="text-[13px] font-bold text-slate-700 mb-4">How connectors work</p>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            {[
              { step: "1", icon: Plus,          title: "Add connector",       desc: "Register your carrier's API, SFTP, webhook, or email endpoint." },
              { step: "2", icon: Settings,       title: "Set Healthy",         desc: "Change operational state to Healthy to enable data sync." },
              { step: "3", icon: RefreshCw,      title: "Sync / Receive data", desc: "Trigger manually or let carriers push invoices via webhook." },
              { step: "4", icon: CheckCircle2,   title: "Cases auto-created",  desc: "Zoiko validates each invoice, detects overcharges, opens cases." },
            ].map(s => {
              const Icon = s.icon;
              return (
                <div key={s.step} className="flex flex-col items-center text-center p-4 rounded-xl bg-slate-50 border border-slate-100">
                  <div className="h-9 w-9 rounded-full bg-blue-600 text-white flex items-center justify-center text-[13px] font-black mb-3 flex-shrink-0">
                    {s.step}
                  </div>
                  <Icon className="h-5 w-5 text-slate-400 mb-2" />
                  <p className="text-[12px] font-bold text-slate-700">{s.title}</p>
                  <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">{s.desc}</p>
                </div>
              );
            })}
          </div>
          <div className="mt-5 text-center">
            <button
              onClick={() => setShowForm(true)}
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-[13px] font-bold transition-colors"
            >
              <Plus className="h-4 w-4" /> Add Your First Connector
            </button>
          </div>
        </div>
      )}

      {/* New connector form */}
      {showForm && (
        <NewConnectorForm
          onClose={() => setShowForm(false)}
          onCreate={form => createMut.mutate(form)}
        />
      )}

      {/* Connector list */}
      {isLoading ? (
        <div className="space-y-3">
          {[1, 2].map(i => (
            <div key={i} className="h-20 bg-white rounded-xl border border-slate-200 animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="space-y-3">
          {connectors.map(c => (
            <ConnectorCard
              key={c.id}
              connector={c}
              onDelete={() => deleteMut.mutate(c.id)}
              onSync={() => syncMut.mutate(c.id)}
              onStateChange={(ops, cert) => stateMut.mutate({ id: c.id, ops, cert })}
            />
          ))}
        </div>
      )}

    </div>
  );
}
