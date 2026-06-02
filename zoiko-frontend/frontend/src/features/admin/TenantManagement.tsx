import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { zoikoApi, type TenantItem, type TenantCreateRequest } from "@/api/zoiko";
import { Building2, Plus, Users, CheckCircle2, XCircle, Loader2, Eye, EyeOff, RefreshCw } from "lucide-react";

const STATUS_STYLE: Record<string, { color: string; bg: string }> = {
  ACTIVE:      { color: "#22c55e", bg: "rgba(34,197,94,0.12)"  },
  SUSPENDED:   { color: "#f59e0b", bg: "rgba(245,158,11,0.12)" },
  OFFBOARDED:  { color: "#ef4444", bg: "rgba(239,68,68,0.12)"  },
};

function slugify(name: string) {
  return name.toLowerCase().trim().replace(/\s+/g, "-").replace(/[^a-z0-9-]/g, "");
}

const EMPTY: TenantCreateRequest = {
  display_name: "", slug: "", admin_email: "", admin_name: "", admin_password: "",
};

export default function TenantManagement() {
  const qc = useQueryClient();

  const { data: tenants = [], isLoading, refetch } = useQuery({
    queryKey: ["tenants"],
    queryFn:  () => zoikoApi.listTenants(),
  });

  const [showForm, setShowForm] = useState(false);
  const [form, setForm]         = useState<TenantCreateRequest>(EMPTY);
  const [showPw, setShowPw]     = useState(false);
  const [success, setSuccess]   = useState("");
  const [error, setError]       = useState("");

  const mutation = useMutation({
    mutationFn: (req: TenantCreateRequest) => zoikoApi.createTenant(req),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["tenants"] });
      setSuccess(`Tenant "${res.display_name}" created. Admin: ${res.admin_email}`);
      setForm(EMPTY);
      setShowForm(false);
      setError("");
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof msg === "string" ? msg : "Failed to create tenant.");
    },
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(""); setSuccess("");
    if (!form.display_name || !form.slug || !form.admin_email || !form.admin_name || !form.admin_password) {
      setError("All fields are required."); return;
    }
    mutation.mutate(form);
  }

  function handleNameChange(val: string) {
    setForm(f => ({ ...f, display_name: val, slug: slugify(val) }));
  }

  return (
    <div>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Building2 style={{ width: 20, height: 20, color: "#60a5fa" }} />
          <div>
            <h1 style={{ fontSize: 18, fontWeight: 700, color: "#1e293b", margin: 0 }}>Tenant Management</h1>
            <p style={{ fontSize: 12, color: "#64748b", margin: 0 }}>Add and manage client companies on this platform</p>
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={() => refetch()} style={btnStyle("ghost")}>
            <RefreshCw style={{ width: 14, height: 14 }} />
          </button>
          <button onClick={() => { setShowForm(true); setSuccess(""); setError(""); }} style={btnStyle("primary")}>
            <Plus style={{ width: 14, height: 14 }} /> Add New Client
          </button>
        </div>
      </div>

      {/* Feedback banners */}
      {success && (
        <div style={{ ...banner, background: "rgba(34,197,94,0.08)", border: "1px solid rgba(34,197,94,0.3)", color: "#16a34a", marginBottom: 16 }}>
          <CheckCircle2 style={{ width: 15, height: 15 }} /> {success}
        </div>
      )}
      {error && (
        <div style={{ ...banner, background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.3)", color: "#dc2626", marginBottom: 16 }}>
          <XCircle style={{ width: 15, height: 15 }} /> {error}
        </div>
      )}

      {/* Add New Client Form */}
      {showForm && (
        <div style={{
          background: "#fff", border: "1px solid #e2e8f0", borderRadius: 12,
          padding: 24, marginBottom: 24, boxShadow: "0 1px 8px rgba(0,0,0,0.06)",
        }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
            <h2 style={{ fontSize: 15, fontWeight: 700, color: "#1e293b", margin: 0 }}>Add New Client</h2>
            <button onClick={() => setShowForm(false)} style={{ background: "none", border: "none", cursor: "pointer", color: "#94a3b8", fontSize: 18 }}>×</button>
          </div>

          <form onSubmit={handleSubmit}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
              <Field label="Company Name" required>
                <input
                  value={form.display_name}
                  onChange={e => handleNameChange(e.target.value)}
                  placeholder="e.g. Amazon India"
                  style={inputStyle}
                />
              </Field>
              <Field label="URL Slug" required hint="Auto-generated, must be unique">
                <input
                  value={form.slug}
                  onChange={e => setForm(f => ({ ...f, slug: slugify(e.target.value) }))}
                  placeholder="e.g. amazon-india"
                  style={inputStyle}
                />
              </Field>
              <Field label="Admin Full Name" required>
                <input
                  value={form.admin_name}
                  onChange={e => setForm(f => ({ ...f, admin_name: e.target.value }))}
                  placeholder="e.g. Ravi Kumar"
                  style={inputStyle}
                />
              </Field>
              <Field label="Admin Email" required>
                <input
                  type="email"
                  value={form.admin_email}
                  onChange={e => setForm(f => ({ ...f, admin_email: e.target.value }))}
                  placeholder="e.g. ravi.k@amazon.in"
                  style={inputStyle}
                />
              </Field>
              <Field label="Admin Password" required>
                <div style={{ position: "relative" }}>
                  <input
                    type={showPw ? "text" : "password"}
                    value={form.admin_password}
                    onChange={e => setForm(f => ({ ...f, admin_password: e.target.value }))}
                    placeholder="Minimum 8 characters"
                    style={{ ...inputStyle, paddingRight: 36 }}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPw(v => !v)}
                    style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", color: "#94a3b8" }}
                  >
                    {showPw ? <EyeOff style={{ width: 15, height: 15 }} /> : <Eye style={{ width: 15, height: 15 }} />}
                  </button>
                </div>
              </Field>
            </div>

            <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: "10px 14px", marginBottom: 16, fontSize: 12, color: "#64748b" }}>
              This creates the tenant record and an <strong>admin</strong> user in one step.
              The admin can then invite analysts and managers from the Users page.
            </div>

            {mutation.error && (
              <div style={{ ...banner, background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.3)", color: "#dc2626", marginBottom: 12 }}>
                <XCircle style={{ width: 14, height: 14 }} /> {error}
              </div>
            )}

            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button type="button" onClick={() => setShowForm(false)} style={btnStyle("ghost")}>Cancel</button>
              <button type="submit" disabled={mutation.isPending} style={btnStyle("primary")}>
                {mutation.isPending
                  ? <><Loader2 style={{ width: 14, height: 14, animation: "spin 1s linear infinite" }} /> Creating…</>
                  : <><Plus style={{ width: 14, height: 14 }} /> Create Tenant</>
                }
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Tenants table */}
      <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 12, overflow: "hidden", boxShadow: "0 1px 4px rgba(0,0,0,0.04)" }}>
        <div style={{ padding: "14px 20px", borderBottom: "1px solid #f1f5f9", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: "#475569" }}>
            {isLoading ? "Loading…" : `${tenants.length} tenant${tenants.length !== 1 ? "s" : ""}`}
          </span>
        </div>

        {isLoading ? (
          <div style={{ padding: 40, textAlign: "center", color: "#94a3b8" }}>
            <Loader2 style={{ width: 20, height: 20, margin: "0 auto 8px", animation: "spin 1s linear infinite" }} />
            <p style={{ fontSize: 13, margin: 0 }}>Loading tenants…</p>
          </div>
        ) : tenants.length === 0 ? (
          <div style={{ padding: 48, textAlign: "center" }}>
            <Building2 style={{ width: 32, height: 32, color: "#cbd5e1", margin: "0 auto 12px" }} />
            <p style={{ fontSize: 14, color: "#64748b", margin: 0 }}>No tenants yet</p>
            <p style={{ fontSize: 12, color: "#94a3b8", marginTop: 4 }}>Click "Add New Client" to onboard your first company</p>
          </div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: "#f8fafc" }}>
                {["Company", "Slug", "Users", "Status", "Created"].map(h => (
                  <th key={h} style={{ padding: "10px 20px", textAlign: "left", fontSize: 11, fontWeight: 700, color: "#94a3b8", letterSpacing: "0.05em", textTransform: "uppercase", borderBottom: "1px solid #f1f5f9" }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {tenants.map((t: TenantItem, i: number) => {
                const sc = STATUS_STYLE[t.status] || STATUS_STYLE.ACTIVE;
                return (
                  <tr key={t.tenant_id} style={{ borderBottom: i < tenants.length - 1 ? "1px solid #f1f5f9" : "none" }}>
                    <td style={{ padding: "14px 20px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <div style={{
                          width: 34, height: 34, borderRadius: 8, flexShrink: 0,
                          background: "linear-gradient(135deg,#3b82f6,#1d4ed8)",
                          display: "flex", alignItems: "center", justifyContent: "center",
                          color: "#fff", fontWeight: 700, fontSize: 13,
                        }}>
                          {t.display_name.charAt(0).toUpperCase()}
                        </div>
                        <span style={{ fontSize: 13, fontWeight: 600, color: "#1e293b" }}>{t.display_name}</span>
                      </div>
                    </td>
                    <td style={{ padding: "14px 20px" }}>
                      <code style={{ fontSize: 12, background: "#f1f5f9", padding: "2px 8px", borderRadius: 4, color: "#475569" }}>{t.slug}</code>
                    </td>
                    <td style={{ padding: "14px 20px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 5, color: "#64748b", fontSize: 13 }}>
                        <Users style={{ width: 13, height: 13 }} />
                        {t.user_count}
                      </div>
                    </td>
                    <td style={{ padding: "14px 20px" }}>
                      <span style={{
                        fontSize: 11, fontWeight: 700, padding: "3px 9px", borderRadius: 99,
                        background: sc.bg, color: sc.color,
                      }}>
                        {t.status}
                      </span>
                    </td>
                    <td style={{ padding: "14px 20px", fontSize: 12, color: "#94a3b8" }}>
                      {new Date(t.created_at).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

function Field({ label, children, required, hint }: {
  label: string; children: React.ReactNode; required?: boolean; hint?: string;
}) {
  return (
    <div>
      <label style={{ fontSize: 12, fontWeight: 600, color: "#475569", display: "block", marginBottom: 5 }}>
        {label}{required && <span style={{ color: "#ef4444", marginLeft: 2 }}>*</span>}
        {hint && <span style={{ fontWeight: 400, color: "#94a3b8", marginLeft: 6 }}>— {hint}</span>}
      </label>
      {children}
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  width: "100%", padding: "8px 12px", borderRadius: 7,
  border: "1px solid #e2e8f0", fontSize: 13, color: "#1e293b",
  outline: "none", boxSizing: "border-box", background: "#fff",
};

const banner: React.CSSProperties = {
  display: "flex", alignItems: "center", gap: 8,
  padding: "9px 14px", borderRadius: 8, fontSize: 13,
};

function btnStyle(variant: "primary" | "ghost"): React.CSSProperties {
  return {
    display: "inline-flex", alignItems: "center", gap: 6,
    padding: variant === "primary" ? "8px 16px" : "8px 10px",
    borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: "pointer",
    border: variant === "primary" ? "none" : "1px solid #e2e8f0",
    background: variant === "primary" ? "#2563eb" : "#fff",
    color:      variant === "primary" ? "#fff"    : "#64748b",
  };
}
