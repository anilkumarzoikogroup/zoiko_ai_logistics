import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { zoikoApi, RegisterRequest } from "@/api/zoiko";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { LoadingSpinner } from "@/components/shared";
import { useToast } from "@/hooks/useToast";
import { formatCurrency } from "@/utils/cn";
import { cn } from "@/utils/cn";
import {
  Users, FileText, Link2, Key, Bell, CreditCard,
  Shield, Check, X, Plus, Trash2, AlertTriangle, Truck, Building2, Pencil,
} from "lucide-react";
import { useAppSelector } from "@/store";

type Tab = "team" | "contracts" | "integrations" | "apikeys" | "notifications" | "billing" | "carriers";

const TABS: { id: Tab; label: string; icon: React.ElementType }[] = [
  { id: "team",          label: "Team & Roles",    icon: Users      },
  { id: "contracts",     label: "Contracts",       icon: FileText   },
  { id: "carriers",      label: "Carriers",        icon: Truck      },
  { id: "integrations",  label: "Integrations",    icon: Link2      },
  { id: "apikeys",       label: "API Keys",        icon: Key        },
  { id: "notifications", label: "Notifications",   icon: Bell       },
  { id: "billing",       label: "Billing",         icon: CreditCard },
];

const ROLE_DESCRIPTIONS: Record<string, { color: string; bg: string; desc: string }> = {
  analyst: { color: "text-blue-700",   bg: "bg-blue-100",   desc: "Submit invoices, propose recovery amounts, view all cases" },
  manager: { color: "text-purple-700", bg: "bg-purple-100", desc: "Approve/reject proposals, execute recovery, view analytics" },
  admin:   { color: "text-slate-700",  bg: "bg-slate-100",  desc: "Full access including settings, user management, audit logs" },
};


const INTEGRATIONS = [
  { name: "Kafka Event Bus",      status: "connected", desc: "17 topics · Amazon MSK · us-east-1" },
  { name: "PostgreSQL Database",  status: "connected", desc: "zoiko DB · 26 tables · localhost:5432" },
  { name: "OPA Policy Engine",    status: "connected", desc: "v0.58 · localhost:8181 · fail-closed" },
  { name: "BlueDart Connector",   status: "connected", desc: "REST API v2 · cert valid until Jun 2025" },
  { name: "Delhivery Connector",  status: "warning",   desc: "Intermittent 503 errors · auto-retry on" },
  { name: "Redis Cache",          status: "connected", desc: "Token CONSUMED lock · 15-min TTL" },
  { name: "SMTP Notifications",   status: "disconnected", desc: "Not configured" },
];

function TeamTab() {
  const qc      = useQueryClient();
  const toast   = useToast();
  const role    = useAppSelector(s => s.auth.role);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm]         = useState<RegisterRequest>({ email: "", password: "", full_name: "", role: "analyst" });
  const [formErr, setFormErr]   = useState("");

  const usersQ = useQuery({
    queryKey: ["settings-users"],
    queryFn:  () => zoikoApi.listUsers(),
    enabled:  role === "admin",
  });

  const createM = useMutation({
    mutationFn: (req: RegisterRequest) => zoikoApi.registerUser(req),
    onSuccess: (u) => {
      qc.invalidateQueries({ queryKey: ["settings-users"] });
      toast.success("User created", `${u.full_name} (${u.role}) can now log in.`);
      setForm({ email: "", password: "", full_name: "", role: "analyst" });
      setShowForm(false);
      setFormErr("");
    },
    onError: (e: any) => {
      const msg = e?.response?.data?.detail;
      setFormErr(typeof msg === "string" ? msg : "Failed to create user.");
    },
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="font-semibold">Team Members</p>
          <p className="text-sm text-muted-foreground mt-0.5">Roles are enforced by OPA policies — changes take effect immediately.</p>
        </div>
        <Button size="sm" className="gap-2" onClick={() => { setShowForm(v => !v); setFormErr(""); }}>
          {showForm ? <X className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
          {showForm ? "Cancel" : "Add Member"}
        </Button>
      </div>

      {/* Role legend */}
      <div className="grid grid-cols-3 gap-3">
        {Object.entries(ROLE_DESCRIPTIONS).map(([role, cfg]) => (
          <div key={role} className={cn("rounded-lg border px-3 py-2.5", cfg.bg)}>
            <div className="flex items-center gap-2 mb-1">
              <span className={cn("text-xs font-bold capitalize", cfg.color)}>{role}</span>
              <Shield className={cn("h-3 w-3", cfg.color)} />
            </div>
            <p className="text-[10px] text-muted-foreground leading-tight">{cfg.desc}</p>
          </div>
        ))}
      </div>

      {/* Add member form */}
      {showForm && (
        <div className="rounded-xl border border-blue-200 bg-blue-50/40 p-5 space-y-3">
          <p className="text-sm font-bold text-slate-700">New Team Member</p>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600">Full Name</label>
              <input type="text" placeholder="Ramu Sharma"
                value={form.full_name}
                onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))}
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600">Work Email</label>
              <input type="email" placeholder="ramu@amazon.in"
                value={form.email}
                onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600">Password</label>
              <input type="password" placeholder="Min 8 characters"
                value={form.password}
                onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600">Role</label>
              <select value={form.role}
                onChange={e => setForm(f => ({ ...f, role: e.target.value as RegisterRequest["role"] }))}
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
                <option value="analyst">Analyst — proposes recoveries</option>
                <option value="manager">Manager — approves recoveries</option>
              </select>
            </div>
          </div>
          {formErr && (
            <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{formErr}</p>
          )}
          <button
            disabled={createM.isPending || !form.email || !form.password || !form.full_name}
            onClick={() => createM.mutate(form)}
            className={cn(
              "w-full flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-semibold transition-colors",
              !createM.isPending && form.email && form.password && form.full_name
                ? "bg-blue-600 hover:bg-blue-700 text-white"
                : "bg-slate-200 text-slate-400 cursor-not-allowed"
            )}
          >
            {createM.isPending ? (
              <><div className="h-4 w-4 rounded-full border-2 border-white/40 border-t-white animate-spin" /> Creating…</>
            ) : (
              <><Plus className="h-4 w-4" /> Create User</>
            )}
          </button>
        </div>
      )}

      {/* Members table */}
      <Card>
        <CardContent className="pt-0">
          {usersQ.isLoading ? (
            <div className="py-6 text-center text-sm text-muted-foreground">Loading team members…</div>
          ) : usersQ.data && usersQ.data.length > 0 ? (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-[10px] uppercase tracking-wide text-muted-foreground">
                <th className="text-left py-3 font-medium">Name</th>
                <th className="text-left py-3 font-medium">Email</th>
                <th className="text-left py-3 font-medium">Role</th>
                <th className="text-center py-3 font-medium">Status</th>
                <th className="text-left py-3 font-medium">Joined</th>
                <th className="py-3" />
              </tr>
            </thead>
            <tbody className="divide-y">
              {usersQ.data.map(m => {
                const roleCfg = ROLE_DESCRIPTIONS[m.role] ?? ROLE_DESCRIPTIONS.analyst;
                return (
                  <tr key={m.user_id} className="hover:bg-secondary/30">
                    <td className="py-3">
                      <div className="flex items-center gap-2.5">
                        <div className={cn("h-7 w-7 rounded-full flex items-center justify-center text-white text-xs font-bold flex-shrink-0", m.role === "admin" ? "bg-slate-700" : m.role === "manager" ? "bg-purple-600" : "bg-blue-600")}>
                          {m.full_name.split(" ").map((w: string) => w[0]).join("").slice(0,2).toUpperCase()}
                        </div>
                        <span className="font-medium">{m.full_name}</span>
                      </div>
                    </td>
                    <td className="py-3 text-xs text-muted-foreground">{m.email}</td>
                    <td className="py-3">
                      <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded-full capitalize", roleCfg.bg, roleCfg.color)}>
                        {m.role}
                      </span>
                    </td>
                    <td className="py-3 text-center">
                      {m.is_active
                        ? <Check className="h-4 w-4 text-emerald-600 mx-auto" />
                        : <X className="h-4 w-4 text-amber-500 mx-auto" />
                      }
                    </td>
                    <td className="py-3 text-xs text-muted-foreground">
                      {new Date(m.created_at).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}
                    </td>
                    <td className="py-3 text-right">
                      <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded-full", m.is_active ? "bg-emerald-100 text-emerald-700" : "bg-gray-100 text-gray-600")}>
                        {m.is_active ? "ACTIVE" : "INACTIVE"}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          ) : (
            <div className="py-10 text-center text-muted-foreground space-y-2">
              <Users className="h-8 w-8 mx-auto text-slate-300" />
              <p className="font-medium">No team members yet</p>
              <p className="text-xs">Click "Add Member" above to invite users to your organization.</p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

const CARRIERS = ["BlueDart","Delhivery","FedEx","DTDC","Ekart","Gati","UPS India","Other"];

function ContractsTab() {
  const qc    = useQueryClient();
  const toast = useToast();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ carrier_id: "", rate_value: "", currency: "INR", effective_on: "2025-01-01" });

  const { data: rates, isLoading } = useQuery({
    queryKey: ["contract-rates"],
    queryFn: zoikoApi.listContractRates,
  });

  const addMutation = useMutation({
    mutationFn: () => zoikoApi.createContractRate({
      carrier_id:   form.carrier_id,
      rate_type:    "fuel_charge",
      rate_value:   Number(form.rate_value),
      currency:     form.currency,
      effective_on: form.effective_on,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["contract-rates"] });
      setShowForm(false);
      setForm({ carrier_id: "", rate_value: "", currency: "INR", effective_on: "2025-01-01" });
      toast.success("Rate saved", `${form.carrier_id} contract rate added — overcharge detection active`);
    },
    onError: () => {
      toast.error("Save failed", "Check that the backend is running on port 8000");
    },
  });

  const delMutation = useMutation({
    mutationFn: (id: string) => zoikoApi.deleteContractRate(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["contract-rates"] });
      toast.info("Rate deleted", "Contract rate removed");
    },
    onError: () => {
      toast.error("Delete failed", "Check that the backend is running on port 8000");
    },
  });

  const canAdd = form.carrier_id && Number(form.rate_value) > 0;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <p className="font-semibold">Carrier Contract Rates</p>
          <p className="text-sm text-muted-foreground mt-0.5">
            These rates are the <strong>source of truth</strong> for overcharge detection.
            When an invoice arrives, its amount is compared against the contract rate for that carrier.
            If invoice &gt; contract rate → overcharge detected → dispute case opened automatically.
          </p>
        </div>
        <Button size="sm" className="gap-2 flex-shrink-0 ml-4" onClick={() => setShowForm(s => !s)}>
          <Plus className="h-4 w-4" /> Add Rate
        </Button>
      </div>

      {/* How it works explanation */}
      <div className="rounded-lg bg-blue-50 border border-blue-200 px-4 py-3 flex gap-3 text-xs text-blue-800">
        <AlertTriangle className="h-4 w-4 text-blue-500 flex-shrink-0 mt-0.5" />
        <div className="space-y-1">
          <p className="font-semibold">How contract rates work</p>
          <p>Example: BlueDart rate = <strong>₹8,000</strong>. BlueDart bills <strong>₹12,500</strong>.</p>
          <p>Validation engine: <code className="bg-blue-100 px-1 rounded">12,500 &gt; 8,000 → FAIL → overcharge = ₹4,500 → case opened</code></p>
          <p>If no rate exists for a carrier → status = WARN, case opened with full amount as overcharge.</p>
        </div>
      </div>

      {/* Add rate form */}
      {showForm && (
        <Card className="border-zoiko-navy/30 bg-zoiko-navy/3">
          <CardContent className="pt-4 pb-4">
            <p className="text-sm font-semibold mb-3">New Contract Rate</p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div>
                <label className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium block mb-1">Carrier</label>
                <select value={form.carrier_id} onChange={e => setForm(f => ({ ...f, carrier_id: e.target.value }))}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring">
                  <option value="">Select…</option>
                  {CARRIERS.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium block mb-1">Max Rate (contract)</label>
                <Input type="number" placeholder="e.g. 8000" value={form.rate_value}
                  onChange={e => setForm(f => ({ ...f, rate_value: e.target.value }))} />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium block mb-1">Currency</label>
                <select value={form.currency} onChange={e => setForm(f => ({ ...f, currency: e.target.value }))}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring">
                  {["INR","USD","EUR"].map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium block mb-1">Effective From</label>
                <input type="date" value={form.effective_on} onChange={e => setForm(f => ({ ...f, effective_on: e.target.value }))}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
              </div>
            </div>
            {form.carrier_id && form.rate_value && (
              <p className="text-xs text-muted-foreground mt-2">
                Any {form.carrier_id} invoice above <strong>{form.currency} {Number(form.rate_value).toLocaleString()}</strong> will trigger an overcharge dispute.
              </p>
            )}
            <div className="flex gap-2 mt-3">
              <Button size="sm" disabled={!canAdd || addMutation.isPending} onClick={() => addMutation.mutate()} className="gap-2">
                {addMutation.isPending ? <><div className="h-3.5 w-3.5 rounded-full border-2 border-white border-t-transparent animate-spin" />Saving…</> : <><Check className="h-3.5 w-3.5" />Save Rate</>}
              </Button>
              <Button size="sm" variant="outline" onClick={() => setShowForm(false)}>Cancel</Button>
              {addMutation.isError && <p className="text-xs text-destructive self-center">Save failed — is the backend running?</p>}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Rates table */}
      <Card>
        <CardContent className="pt-0">
          {isLoading ? <LoadingSpinner /> : !rates || rates.length === 0 ? (
            <div className="py-10 text-center text-muted-foreground space-y-2">
              <AlertTriangle className="h-8 w-8 mx-auto text-amber-400" />
              <p className="font-medium text-amber-700">No contract rates found</p>
              <p className="text-xs">Without rates, all invoices return WARN instead of FAIL. Click "Add Rate" to seed them,<br />or run <code className="bg-secondary px-1 rounded">python seed_contract_rates.py</code> in backend/gateway/.</p>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-[10px] uppercase tracking-wide text-muted-foreground">
                  <th className="text-left py-3 font-medium">Carrier</th>
                  <th className="text-left py-3 font-medium">Rate Type</th>
                  <th className="text-right py-3 font-medium">Max Allowed</th>
                  <th className="text-left py-3 font-medium">Effective From</th>
                  <th className="text-left py-3 font-medium">Expires</th>
                  <th className="text-left py-3 font-medium">Status</th>
                  <th className="py-3" />
                </tr>
              </thead>
              <tbody className="divide-y">
                {rates.map(r => {
                  const expired = r.expires_on && new Date(r.expires_on) < new Date();
                  return (
                    <tr key={r.id} className="hover:bg-secondary/30">
                      <td className="py-3 font-semibold">{r.carrier}</td>
                      <td className="py-3 text-xs text-muted-foreground font-mono">{r.rate_type}</td>
                      <td className="py-3 text-right font-bold text-emerald-700">{formatCurrency(r.rate_value, r.currency)}</td>
                      <td className="py-3 text-xs text-muted-foreground">{r.effective_on}</td>
                      <td className="py-3 text-xs text-muted-foreground">{r.expires_on ?? "Never"}</td>
                      <td className="py-3">
                        <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded-full",
                          expired ? "bg-red-100 text-red-700" : "bg-emerald-100 text-emerald-700"
                        )}>
                          {expired ? "EXPIRED" : "ACTIVE"}
                        </span>
                      </td>
                      <td className="py-3 text-right">
                        <button onClick={() => delMutation.mutate(r.id)}
                          className="text-muted-foreground hover:text-destructive transition-colors"
                          title="Delete rate">
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function IntegrationsTab() {
  return (
    <div className="space-y-3">
      {INTEGRATIONS.map(intg => (
        <div key={intg.name} className={cn(
          "flex items-center justify-between rounded-xl border px-5 py-4",
          intg.status === "connected" ? "bg-white" : intg.status === "warning" ? "bg-amber-50 border-amber-200" : "bg-gray-50"
        )}>
          <div className="flex items-center gap-3">
            <div className={cn("h-2.5 w-2.5 rounded-full flex-shrink-0",
              intg.status === "connected" ? "bg-emerald-500" : intg.status === "warning" ? "bg-amber-500" : "bg-gray-400"
            )} />
            <div>
              <p className="font-semibold text-sm">{intg.name}</p>
              <p className="text-xs text-muted-foreground">{intg.desc}</p>
            </div>
          </div>
          <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded-full",
            intg.status === "connected" ? "bg-emerald-100 text-emerald-700" :
            intg.status === "warning"   ? "bg-amber-100 text-amber-700" :
            "bg-gray-100 text-gray-500"
          )}>
            {intg.status.toUpperCase()}
          </span>
        </div>
      ))}
    </div>
  );
}

function ApiKeysTab() {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">API keys for programmatic access. Keys are scoped to your tenant.</p>
        <Button size="sm" className="gap-2"><Plus className="h-4 w-4" /> Generate Key</Button>
      </div>
      <Card>
        <CardContent className="pt-5 space-y-3">
          {[
            { name: "CI Pipeline Key",    key: "zk_live_••••••••••••••••a3f7", scopes: "read:cases,write:cases", created: "Jan 10, 2025", last_used: "2 min ago" },
            { name: "Dashboard Key",      key: "zk_live_••••••••••••••••c2e9", scopes: "read:*",                 created: "Jan 12, 2025", last_used: "1 hr ago"  },
          ].map(k => (
            <div key={k.name} className="rounded-lg border px-4 py-3 flex items-center justify-between gap-4">
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-sm">{k.name}</p>
                <code className="text-[10px] text-muted-foreground">{k.key}</code>
                <p className="text-[10px] text-muted-foreground mt-0.5">Scopes: {k.scopes} · Created {k.created} · Last used {k.last_used}</p>
              </div>
              <Button variant="outline" size="sm" className="text-destructive hover:text-destructive flex-shrink-0">Revoke</Button>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

function PlaceholderTab({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-muted-foreground gap-3">
      <div className="h-14 w-14 rounded-full bg-secondary flex items-center justify-center">
        <Bell className="h-7 w-7 text-muted-foreground/50" />
      </div>
      <p className="font-medium">{label} settings coming soon</p>
    </div>
  );
}

function CarriersTab() {
  const qc = useQueryClient();
  const toast = useToast();
  const [showForm, setShowForm] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [form, setForm] = useState({ name: "", email: "", address: "", contact_person: "", contact_phone: "", cc_emails: "" });

  const carriersQ = useQuery({
    queryKey: ["carriers"],
    queryFn: zoikoApi.listCarriers,
  });

  const createM = useMutation({
    mutationFn: () => zoikoApi.createCarrier(form),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["carriers"] });
      toast.success("Carrier added", r.name);
      resetForm();
    },
    onError: (e: any) => toast.error("Failed", e?.response?.data?.detail || "Error"),
  });

  const updateM = useMutation({
    mutationFn: () => zoikoApi.updateCarrier(editId!, form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["carriers"] });
      toast.success("Carrier updated", form.name);
      resetForm();
    },
    onError: (e: any) => toast.error("Failed", e?.response?.data?.detail || "Error"),
  });

  const deleteM = useMutation({
    mutationFn: (id: string) => zoikoApi.deleteCarrier(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["carriers"] });
      toast.info("Carrier removed", "");
    },
    onError: (e: any) => toast.error("Failed", e?.response?.data?.detail || "Error"),
  });

  function resetForm() {
    setShowForm(false);
    setEditId(null);
    setForm({ name: "", email: "", address: "", contact_person: "", contact_phone: "", cc_emails: "" });
  }

  function editCarrier(c: any) {
    setEditId(c.id);
    setForm({ name: c.name, email: c.email, address: c.address, contact_person: c.contact_person, contact_phone: c.contact_phone, cc_emails: c.cc_emails || "" });
    setShowForm(true);
  }

  const saving = createM.isPending || updateM.isPending;
  const canSave = form.name.trim().length > 0;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="font-semibold">Carrier Contacts</p>
          <p className="text-sm text-muted-foreground mt-0.5">Store carrier email & address so dispute letters are auto-populated.</p>
        </div>
        <Button size="sm" className="gap-2" onClick={() => { resetForm(); setShowForm(v => !v); }}>
          {showForm ? <X className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
          {showForm ? "Cancel" : "Add Carrier"}
        </Button>
      </div>

      {showForm && (
        <div className="rounded-xl border border-blue-200 bg-blue-50/40 p-5 space-y-3">
          <p className="text-sm font-bold text-slate-700">{editId ? "Edit" : "New"} Carrier</p>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600">Carrier Name *</label>
              <input type="text" placeholder="Delhivery"
                value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600">Email</label>
              <input type="email" placeholder="accounts@delhivery.com"
                value={form.email}
                onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
            <div className="col-span-2 space-y-1">
              <label className="text-xs font-medium text-slate-600">Address</label>
              <input type="text" placeholder="123 Carrier St, New Delhi"
                value={form.address}
                onChange={e => setForm(f => ({ ...f, address: e.target.value }))}
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600">Contact Person</label>
              <input type="text" placeholder="Ravi Sharma"
                value={form.contact_person}
                onChange={e => setForm(f => ({ ...f, contact_person: e.target.value }))}
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600">Phone</label>
              <input type="text" placeholder="+91 98765 43210"
                value={form.contact_phone}
                onChange={e => setForm(f => ({ ...f, contact_phone: e.target.value }))}
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
            <div className="col-span-2 space-y-1">
              <label className="text-xs font-medium text-slate-600">CC Emails <span className="text-muted-foreground font-normal">(comma-separated — auto-CC'd when sending dispute)</span></label>
              <input type="text" placeholder="finance@bluedart.com, disputes@bluedart.com"
                value={form.cc_emails}
                onChange={e => setForm(f => ({ ...f, cc_emails: e.target.value }))}
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
          </div>
          <button
            disabled={saving || !canSave}
            onClick={() => editId ? updateM.mutate() : createM.mutate()}
            className={cn(
              "w-full flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-semibold transition-colors",
              saving || !canSave ? "bg-slate-200 text-slate-400 cursor-not-allowed" : "bg-blue-600 hover:bg-blue-700 text-white"
            )}
          >
            {saving ? <><div className="h-4 w-4 rounded-full border-2 border-white/40 border-t-white animate-spin" /> Saving…</> : <>{editId ? "Update" : "Save"} Carrier</>}
          </button>
        </div>
      )}

      <Card>
        <CardContent className="pt-0">
          {carriersQ.isLoading ? (
            <div className="py-6 text-center text-sm text-muted-foreground">Loading carriers…</div>
          ) : carriersQ.data && carriersQ.data.length > 0 ? (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-[10px] uppercase tracking-wide text-muted-foreground">
                  <th className="text-left py-3 font-medium">Carrier</th>
                  <th className="text-left py-3 font-medium">Email</th>
                  <th className="text-left py-3 font-medium">Contact</th>
                  <th className="py-3" />
                </tr>
              </thead>
              <tbody className="divide-y">
                {carriersQ.data.map(c => (
                  <tr key={c.id} className="hover:bg-secondary/30">
                    <td className="py-3 font-semibold">{c.name}</td>
                    <td className="py-3 text-xs text-muted-foreground">{c.email || "—"}</td>
                    <td className="py-3">
                      <span className="text-xs text-muted-foreground">{c.contact_person ? `${c.contact_person} ${c.contact_phone ? `· ${c.contact_phone}` : ""}` : "—"}</span>
                    </td>
                    <td className="py-3 text-right">
                      <button onClick={() => editCarrier(c)} className="text-muted-foreground hover:text-blue-600 mx-1" title="Edit"><Pencil className="h-3.5 w-3.5 inline" /></button>
                      <button onClick={() => deleteM.mutate(c.id)} className="text-muted-foreground hover:text-red-600 mx-1" title="Delete"><Trash2 className="h-3.5 w-3.5 inline" /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="py-10 text-center text-muted-foreground space-y-2">
              <Truck className="h-8 w-8 mx-auto text-slate-300" />
              <p className="font-medium">No carriers configured</p>
              <p className="text-xs">Add carriers so dispute letters auto-populate their email and address.</p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function Settings() {
  const [activeTab, setActiveTab] = useState<Tab>("team");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-zoiko-navy">Settings</h1>
        <p className="text-sm text-muted-foreground mt-1">Manage your team, contracts, integrations, and platform configuration.</p>
      </div>

      <div className="flex gap-1 border-b overflow-x-auto">
        {TABS.map(tab => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px whitespace-nowrap",
                activeTab === tab.id
                  ? "border-zoiko-navy text-zoiko-navy"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              )}
            >
              <Icon className="h-4 w-4" />
              {tab.label}
            </button>
          );
        })}
      </div>

      <div>
        {activeTab === "team"          && <TeamTab />}
        {activeTab === "contracts"     && <ContractsTab />}
        {activeTab === "carriers"      && <CarriersTab />}
        {activeTab === "integrations"  && <IntegrationsTab />}
        {activeTab === "apikeys"       && <ApiKeysTab />}
        {activeTab === "notifications" && <PlaceholderTab label="Notification" />}
        {activeTab === "billing"       && <PlaceholderTab label="Billing" />}
      </div>
    </div>
  );
}
