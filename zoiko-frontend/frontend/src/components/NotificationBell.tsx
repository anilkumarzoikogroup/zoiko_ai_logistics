/**
 * NotificationBell — real-time notification centre.
 *
 * Queries the live cases + tokens API every 30s and derives notifications:
 *   • FINDING_GENERATED  → "Analyst review needed"
 *   • APPROVAL_PENDING   → "Manager approval needed"
 *   • EXECUTION_READY    → "Recovery ready to execute"
 *   • ACTIVE token       → "Governance token expiring"
 *   • Newly opened cases → "New case opened"
 *
 * Badge count = total urgent items needing action.
 * Dropdown shows each notification with time-ago, type icon, and quick link.
 */
import { useState, useRef, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { zoikoApi } from "@/api/zoiko";
import {
  Bell, Brain, CheckCircle2, Zap, Clock,
  FileText, ArrowRight, Check,
} from "lucide-react";
import type { Case, GovernanceToken } from "@/types";

// ── Types ─────────────────────────────────────────────────────────────────────
interface Notification {
  id:      string;
  type:    "proposal" | "approval" | "execute" | "token" | "new_case";
  title:   string;
  body:    string;
  time:    Date;
  to:      string;
  read:    boolean;
  urgent:  boolean;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function timeAgo(d: Date): string {
  const s = Math.floor((Date.now() - d.getTime()) / 1000);
  if (s < 60)    return "just now";
  if (s < 3600)  return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

const TYPE_CFG = {
  proposal: { icon: Brain,        color: "#7c3aed", label: "Review needed"   },
  approval: { icon: CheckCircle2, color: "#d97706", label: "Approval needed" },
  execute:  { icon: Zap,          color: "#2563eb", label: "Ready to execute"},
  token:    { icon: Clock,        color: "#dc2626", label: "Token expiring"  },
  new_case: { icon: FileText,     color: "#64748b", label: "New case"        },
};

interface Props { isDark: boolean; role: string; }

export default function NotificationBell({ isDark, role }: Props) {
  const nav = useNavigate();
  const [open, setOpen]   = useState(false);
  const [read, setRead]   = useState<Set<string>>(new Set());
  const ref               = useRef<HTMLDivElement>(null);

  // ── Live data — refetch every 30s ─────────────────────────────────────────
  const { data: cases  = [] } = useQuery({
    queryKey: ["cases"],
    queryFn:  () => zoikoApi.listCases(),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });
  const { data: tokens = [] } = useQuery({
    queryKey: ["tokens"],
    queryFn:  () => zoikoApi.listTokens(),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });

  // ── Derive notifications from live data ───────────────────────────────────
  const notifications = useMemo<Notification[]>(() => {
    const list: Notification[] = [];

    (cases as Case[]).forEach(c => {
      const t = new Date(c.opened_at);

      if (c.state === "FINDING_GENERATED" && (role === "analyst" || role === "admin")) {
        list.push({
          id: `prop-${c.id}`, type: "proposal", urgent: true, read: false, to: "/analyst", time: t,
          title: "Analyst review needed",
          body:  `${c.carrier || "Case"} · ${c.currency} ${c.diff > 0 ? c.diff.toLocaleString("en-IN") : c.amount.toLocaleString("en-IN")} overcharge detected`,
        });
      }
      if (c.state === "APPROVAL_PENDING" && (role === "manager" || role === "admin")) {
        list.push({
          id: `appr-${c.id}`, type: "approval", urgent: true, read: false, to: "/manager", time: t,
          title: "Approval required",
          body:  `${c.carrier || "Case"} · Recovery of ${c.currency} ${(c.diff || 0).toLocaleString("en-IN")} awaiting your approval`,
        });
      }
      if (c.state === "EXECUTION_READY" && (role === "manager" || role === "admin")) {
        list.push({
          id: `exec-${c.id}`, type: "execute", urgent: true, read: false, to: "/execute", time: t,
          title: "Recovery ready to execute",
          body:  `${c.carrier || "Case"} · Governance token active — 15-min window`,
        });
      }
      // Newly opened cases (last 24h)
      if (c.state === "NEW" || c.state === "EVIDENCE_PENDING") {
        const ageH = (Date.now() - t.getTime()) / 3_600_000;
        if (ageH < 24) {
          list.push({
            id: `new-${c.id}`, type: "new_case", urgent: false, read: false,
            to: `/cases/${c.id}`, time: t,
            title: "New case opened",
            body:  `${c.carrier || "Carrier"} · ${c.currency} ${c.amount.toLocaleString("en-IN")}`,
          });
        }
      }
    });

    // Active governance tokens
    (tokens as GovernanceToken[]).filter(t => t.status === "ACTIVE").forEach(t => {
      const exp  = new Date(t.exp || "");
      const minsLeft = Math.round((exp.getTime() - Date.now()) / 60_000);
      if (!isNaN(minsLeft) && minsLeft > 0 && minsLeft <= 15) {
        list.push({
          id: `tok-${t.id}`, type: "token", urgent: true, read: false, to: "/execute",
          time: new Date(),
          title: "Governance token expiring",
          body: `${minsLeft} min remaining — execute now to recover funds`,
        });
      }
    });

    // Sort: urgent first, then by time desc
    return list.sort((a, b) =>
      a.urgent === b.urgent ? b.time.getTime() - a.time.getTime() : a.urgent ? -1 : 1
    );
  }, [cases, tokens, role]);

  const unread = notifications.filter(n => !read.has(n.id)).length;

  // Close on outside click
  useEffect(() => {
    function handle(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, []);

  function markAllRead() {
    setRead(new Set(notifications.map(n => n.id)));
  }
  function markRead(id: string) {
    setRead(prev => new Set([...prev, id]));
  }
  function openNotification(n: Notification) {
    markRead(n.id); nav(n.to); setOpen(false);
  }

  // Theme
  const bg     = isDark ? "#0d1424" : "#ffffff";
  const border = isDark ? "#1e293b" : "#e2e8f0";
  const text   = isDark ? "#e2e8f0" : "#1e293b";
  const muted  = isDark ? "#475569" : "#94a3b8";
  const hover  = isDark ? "#0d1a2e" : "#f8fafc";
  const divBg  = isDark ? "#0a0f1e" : "#f1f5f9";
  const readBg = isDark ? "rgba(255,255,255,0.02)" : "rgba(0,0,0,0.01)";

  return (
    <div ref={ref} style={{ position: "relative" }}>
      {/* Bell button */}
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          position: "relative", padding: 8, borderRadius: 8,
          background: "transparent", border: "none", cursor: "pointer",
          transition: "background 0.15s",
          color: isDark ? "#64748b" : "#64748b",
        }}
        onMouseEnter={e => (e.currentTarget.style.background = isDark ? "rgba(255,255,255,0.06)" : "#f1f5f9")}
        onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
        title="Notifications"
      >
        <Bell style={{ width: 16, height: 16 }} />

        {/* Badge */}
        {unread > 0 && (
          <span style={{
            position: "absolute", top: 3, right: 3,
            minWidth: 16, height: 16, borderRadius: 999,
            background: unread > 0 && notifications.some(n => n.urgent && !read.has(n.id)) ? "#ef4444" : "#64748b",
            fontSize: 9, fontWeight: 800, color: "#fff",
            display: "flex", alignItems: "center", justifyContent: "center",
            padding: "0 3px",
            animation: unread > 0 ? "bellPulse 2s ease-in-out infinite" : "none",
          }}>
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {/* Dropdown */}
      {open && (
        <div style={{
          position: "absolute", top: "calc(100% + 6px)", right: 0, zIndex: 9999,
          background: bg, border: `1px solid ${border}`, borderRadius: 12,
          boxShadow: isDark ? "0 8px 40px rgba(0,0,0,0.7)" : "0 8px 40px rgba(0,0,0,0.14)",
          width: 340, maxHeight: 500, display: "flex", flexDirection: "column", overflow: "hidden",
        }}>

          {/* Header */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 16px 10px", borderBottom: `1px solid ${border}`, background: divBg, flexShrink: 0 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
              <Bell style={{ width: 14, height: 14, color: muted }} />
              <span style={{ fontSize: 13, fontWeight: 700, color: text }}>Notifications</span>
              {unread > 0 && (
                <span style={{ fontSize: 10, fontWeight: 700, background: "#ef4444", color: "#fff", padding: "1px 6px", borderRadius: 99 }}>
                  {unread} new
                </span>
              )}
            </div>
            {unread > 0 && (
              <button onClick={markAllRead} style={{ fontSize: 11, color: "#3b82f6", background: "none", border: "none", cursor: "pointer", fontWeight: 600, display: "flex", alignItems: "center", gap: 3 }}>
                <Check style={{ width: 11, height: 11 }} /> Mark all read
              </button>
            )}
          </div>

          {/* List */}
          <div style={{ flex: 1, overflowY: "auto" }}>
            {notifications.length === 0 ? (
              <div style={{ padding: "32px 16px", textAlign: "center" }}>
                <Bell style={{ width: 28, height: 28, color: muted, margin: "0 auto 10px" }} />
                <p style={{ fontSize: 13, color: text, margin: 0, fontWeight: 600 }}>All caught up!</p>
                <p style={{ fontSize: 11, color: muted, margin: "4px 0 0" }}>No pending actions right now.</p>
              </div>
            ) : (
              notifications.map((n, i) => {
                const isRead = read.has(n.id);
                const cfg = TYPE_CFG[n.type];
                const Icon = cfg.icon;
                return (
                  <div
                    key={n.id}
                    onClick={() => openNotification(n)}
                    style={{
                      display: "flex", gap: 10, padding: "11px 14px",
                      borderBottom: i < notifications.length - 1 ? `1px solid ${border}` : "none",
                      background: isRead ? readBg : (isDark ? "rgba(59,130,246,0.04)" : "rgba(59,130,246,0.03)"),
                      cursor: "pointer", transition: "background 0.1s", position: "relative",
                    }}
                    onMouseEnter={e => (e.currentTarget.style.background = hover)}
                    onMouseLeave={e => (e.currentTarget.style.background = isRead ? readBg : (isDark ? "rgba(59,130,246,0.04)" : "rgba(59,130,246,0.03)"))}
                  >
                    {/* Unread dot */}
                    {!isRead && (
                      <div style={{ position: "absolute", left: 4, top: "50%", transform: "translateY(-50%)", width: 5, height: 5, borderRadius: "50%", background: cfg.color }} />
                    )}

                    {/* Icon */}
                    <div style={{ width: 34, height: 34, borderRadius: 8, background: cfg.color + "18", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, marginTop: 1 }}>
                      <Icon style={{ width: 15, height: 15, color: cfg.color }} />
                    </div>

                    {/* Content */}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 2 }}>
                        <span style={{ fontSize: 12, fontWeight: isRead ? 500 : 700, color: text, flex: 1, marginRight: 6, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                          {n.title}
                        </span>
                        <span style={{ fontSize: 10, color: muted, flexShrink: 0 }}>{timeAgo(n.time)}</span>
                      </div>
                      <p style={{ fontSize: 11, color: muted, margin: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                        {n.body}
                      </p>
                      {n.urgent && !isRead && (
                        <span style={{ display: "inline-block", marginTop: 4, fontSize: 9, fontWeight: 700, color: cfg.color, background: cfg.color + "18", padding: "1px 6px", borderRadius: 99 }}>
                          {cfg.label}
                        </span>
                      )}
                    </div>

                    {/* Arrow */}
                    <ArrowRight style={{ width: 12, height: 12, color: muted, flexShrink: 0, marginTop: 8 }} />
                  </div>
                );
              })
            )}
          </div>

          {/* Footer */}
          <div style={{ borderTop: `1px solid ${border}`, padding: "9px 14px", background: divBg, flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ fontSize: 10, color: muted }}>
              Refreshes every 30s · {notifications.length} total
            </span>
            <button
              onClick={() => { nav("/cases"); setOpen(false); }}
              style={{ fontSize: 11, color: "#3b82f6", background: "none", border: "none", cursor: "pointer", fontWeight: 600, display: "flex", alignItems: "center", gap: 3 }}
            >
              View all cases <ArrowRight style={{ width: 11, height: 11 }} />
            </button>
          </div>
        </div>
      )}

      {/* Keyframe for bell pulse */}
      <style>{`
        @keyframes bellPulse {
          0%, 100% { transform: scale(1); }
          50% { transform: scale(1.15); }
        }
      `}</style>
    </div>
  );
}
