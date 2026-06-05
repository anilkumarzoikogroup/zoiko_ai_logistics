import { useQuery } from "@tanstack/react-query";
import { zoikoApi, type TenantItem } from "@/api/zoiko";
import { Building2, Users, Loader2, RefreshCw } from "lucide-react";

const STATUS_STYLE: Record<string, { color: string; bg: string }> = {
  ACTIVE:      { color: "#22c55e", bg: "rgba(34,197,94,0.12)"  },
  SUSPENDED:   { color: "#f59e0b", bg: "rgba(245,158,11,0.12)" },
  OFFBOARDED:  { color: "#ef4444", bg: "rgba(239,68,68,0.12)"  },
};

export default function TenantManagement() {
  const { data: tenants = [], isLoading, refetch } = useQuery({
    queryKey: ["tenants"],
    queryFn:  () => zoikoApi.listTenants(),
  });

  return (
    <div>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Building2 style={{ width: 20, height: 20, color: "#60a5fa" }} />
          <div>
            <h1 style={{ fontSize: 18, fontWeight: 700, color: "#1e293b", margin: 0 }}>My Organization</h1>
            <p style={{ fontSize: 12, color: "#64748b", margin: 0 }}>Your organization details — only your own tenant is visible</p>
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={() => refetch()} style={btnStyle("ghost")}>
            <RefreshCw style={{ width: 14, height: 14 }} />
          </button>
        </div>
      </div>
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
            <p style={{ fontSize: 14, color: "#64748b", margin: 0 }}>No organization info found</p>
            <p style={{ fontSize: 12, color: "#94a3b8", marginTop: 4 }}>Contact support if this persists.</p>
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
                      {new Date(t.created_at).toLocaleDateString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", year: "numeric" })}
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
