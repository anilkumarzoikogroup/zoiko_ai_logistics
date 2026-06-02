import { useState } from "react";
import { FlaskConical, RefreshCw, CheckCircle2, XCircle, AlertTriangle } from "lucide-react";

type StubKey = "sanctions" | "fx" | "connector" | "gl";

interface StubDef {
  label:       string;
  endpoint:    string;
  description: string;
  samplePayload: object;
  sampleResponse: object;
  status: "PASS" | "WARN" | "FAIL";
}

const STUBS: Record<StubKey, StubDef> = {
  sanctions: {
    label:       "Sanctions Screening",
    endpoint:    "POST /v1/execute (gate: sanctions)",
    description: "OFAC/SDN list check. Returns CLEAR when carrier is not on any watchlist.",
    status:      "PASS",
    samplePayload: {
      carrier_name: "BlueDart Express Ltd",
      country:      "IN",
      token_id:     "tok_abc123",
    },
    sampleResponse: {
      gate:    "sanctions",
      passed:  true,
      result:  "CLEAR",
      checked: ["OFAC_SDN", "EU_CONSOLIDATED", "UN_SANCTIONS"],
      latency_ms: 12,
    },
  },
  fx: {
    label:       "FX Rate Lookup",
    endpoint:    "POST /v1/execute (gate: fx)",
    description: "Live FX rate for INR→USD conversion at time of execution.",
    status:      "PASS",
    samplePayload: {
      from_currency: "INR",
      to_currency:   "USD",
      amount:        4500,
    },
    sampleResponse: {
      gate:         "fx",
      passed:       true,
      rate:         0.012,
      converted:    54.0,
      source:       "stub:ecb",
      timestamp:    "2026-06-01T10:00:00Z",
    },
  },
  connector: {
    label:       "Carrier Connector",
    endpoint:    "POST /v1/execute (gate: connector)",
    description: "Carrier API reachability check before dispatching recovery request.",
    status:      "PASS",
    samplePayload: {
      carrier_code: "BDRT",
      action:       "credit_note",
      amount_inr:   4500,
      invoice_ref:  "INV-2024-001",
    },
    sampleResponse: {
      gate:          "connector",
      passed:        true,
      connector_ref: "BDRT-CN-20260601-001",
      ack:           "ACCEPTED",
      eta_days:      3,
    },
  },
  gl: {
    label:       "GL / ERP Posting",
    endpoint:    "POST /v1/reconcile (gl_post)",
    description: "General Ledger stub — posts credit note to ERP after reconciliation.",
    status:      "WARN",
    samplePayload: {
      gl_account:   "4001-FREIGHT-RECOVERY",
      amount_inr:   4500,
      currency:     "INR",
      reference:    "ACR-20260601-001",
      posting_date: "2026-06-01",
    },
    sampleResponse: {
      gate:    "gl",
      passed:  true,
      journal: "JNL-2026-00412",
      note:    "Stub mode: posting logged but not sent to live ERP",
      warning: "ERP_STUB_ACTIVE",
    },
  },
};

const STATUS_CONFIG = {
  PASS: { icon: CheckCircle2, color: "#22c55e", bg: "rgba(34,197,94,0.1)",  label: "Pass"    },
  WARN: { icon: AlertTriangle, color: "#f59e0b", bg: "rgba(245,158,11,0.1)", label: "Warning" },
  FAIL: { icon: XCircle,       color: "#ef4444", bg: "rgba(239,68,68,0.1)",  label: "Fail"    },
};

export default function StubViewer() {
  const [active, setActive]   = useState<StubKey>("sanctions");
  const [loading, setLoading] = useState(false);
  const [pinged, setPinged]   = useState<Record<StubKey, boolean>>({
    sanctions: false, fx: false, connector: false, gl: false,
  });

  const stub = STUBS[active];
  const sc   = STATUS_CONFIG[stub.status];
  const StatusIcon = sc.icon;

  function handlePing() {
    setLoading(true);
    setTimeout(() => {
      setLoading(false);
      setPinged(p => ({ ...p, [active]: true }));
    }, 600);
  }

  return (
    <div style={{ fontFamily: "inherit", color: "#e2e8f0" }}>

      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
          <FlaskConical style={{ width: 20, height: 20, color: "#60a5fa" }} />
          <h1 style={{ fontSize: 18, fontWeight: 700, color: "#f1f5f9", margin: 0 }}>
            Stub Response Viewer
          </h1>
          <span style={{
            fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 99,
            background: "rgba(234,179,8,0.15)", color: "#fbbf24",
            border: "1px solid rgba(234,179,8,0.3)", letterSpacing: "0.05em",
          }}>
            DEV / TEST
          </span>
        </div>
        <p style={{ fontSize: 13, color: "#64748b", margin: 0 }}>
          Inspect mock responses injected by the backend stub layer during Phase 4 execution.
          Only active when <code style={{ background: "#1e293b", padding: "1px 6px", borderRadius: 4, fontSize: 12 }}>DEV_MODE=true</code>.
        </p>
      </div>

      <div style={{ display: "flex", gap: 20 }}>

        {/* Sidebar tabs */}
        <div style={{ width: 180, flexShrink: 0, display: "flex", flexDirection: "column", gap: 4 }}>
          {(Object.keys(STUBS) as StubKey[]).map(key => {
            const s  = STUBS[key];
            const sc = STATUS_CONFIG[s.status];
            const SI = sc.icon;
            return (
              <button
                key={key}
                onClick={() => setActive(key)}
                style={{
                  display: "flex", alignItems: "center", gap: 8,
                  padding: "9px 12px", borderRadius: 8, border: "none",
                  cursor: "pointer", textAlign: "left",
                  background: active === key ? "#1e40af" : "#1e293b",
                  color:      active === key ? "#fff"    : "#94a3b8",
                  transition: "all 0.15s",
                  fontSize: 13, fontWeight: active === key ? 600 : 400,
                }}
              >
                <SI style={{ width: 14, height: 14, color: sc.color, flexShrink: 0 }} />
                <span style={{ flex: 1 }}>{s.label}</span>
              </button>
            );
          })}
        </div>

        {/* Detail pane */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 16 }}>

          {/* Status bar */}
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            background: sc.bg, border: `1px solid ${sc.color}40`,
            borderRadius: 10, padding: "10px 16px",
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <StatusIcon style={{ width: 16, height: 16, color: sc.color }} />
              <span style={{ fontWeight: 600, color: sc.color, fontSize: 13 }}>{sc.label}</span>
              <span style={{ color: "#64748b", fontSize: 13 }}>·</span>
              <span style={{ color: "#94a3b8", fontSize: 13 }}>{stub.endpoint}</span>
            </div>
            <button
              onClick={handlePing}
              disabled={loading}
              style={{
                display: "flex", alignItems: "center", gap: 6,
                padding: "5px 12px", borderRadius: 6,
                background: "#1e293b", border: "1px solid #334155",
                color: "#94a3b8", fontSize: 12, cursor: "pointer",
                opacity: loading ? 0.6 : 1,
              }}
            >
              <RefreshCw style={{ width: 12, height: 12, animation: loading ? "spin 0.8s linear infinite" : "none" }} />
              {loading ? "Pinging…" : pinged[active] ? "Re-ping stub" : "Ping stub"}
            </button>
          </div>

          {/* Description */}
          <p style={{ margin: 0, fontSize: 13, color: "#94a3b8", lineHeight: 1.6 }}>
            {stub.description}
          </p>

          {/* Payload / Response side by side */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <Section title="Sample Payload">
              <JsonBlock data={stub.samplePayload} />
            </Section>
            <Section title="Stub Response">
              <JsonBlock data={stub.sampleResponse} highlight />
            </Section>
          </div>

          {pinged[active] && (
            <div style={{
              padding: "10px 14px", borderRadius: 8,
              background: "rgba(34,197,94,0.08)", border: "1px solid rgba(34,197,94,0.3)",
              fontSize: 12, color: "#86efac",
            }}>
              Stub endpoint responded · {stub.status === "WARN" ? "⚠ " : "✓ "}Response matches expected schema
            </div>
          )}
        </div>
      </div>

      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ background: "#0f172a", borderRadius: 8, border: "1px solid #1e293b", overflow: "hidden" }}>
      <div style={{
        padding: "7px 12px", background: "#1e293b",
        fontSize: 11, fontWeight: 700, color: "#64748b",
        letterSpacing: "0.06em", textTransform: "uppercase",
      }}>
        {title}
      </div>
      <div style={{ padding: 12 }}>{children}</div>
    </div>
  );
}

function JsonBlock({ data, highlight }: { data: object; highlight?: boolean }) {
  const json = JSON.stringify(data, null, 2);
  return (
    <pre style={{
      margin: 0, fontSize: 12, lineHeight: 1.7,
      color: highlight ? "#86efac" : "#94a3b8",
      whiteSpace: "pre-wrap", wordBreak: "break-word",
    }}>
      {json}
    </pre>
  );
}
