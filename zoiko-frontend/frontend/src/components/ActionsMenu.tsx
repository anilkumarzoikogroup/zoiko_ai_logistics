/**
 * ActionsMenu — role-based quick-action dropdown in the top bar.
 * Shows actions relevant to the logged-in user's role and navigates on click.
 */
import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  ChevronDown, FileText, Eye, CheckCircle2,
  Zap, BarChart3, Users, Download, RefreshCw,
  FilePlus, ShieldCheck,
} from "lucide-react";

interface Action {
  label:    string;
  icon:     React.ElementType;
  to?:      string;
  onClick?: () => void;
  divider?: boolean;
  accent?:  string;
  roles:    string[];
}

const ACTIONS: Action[] = [
  // ── Invoice / Submission ─────────────────────────────────────────────
  { label: "Submit New Invoice",     icon: FilePlus,     to: "/cases/new",  accent: "#3b82f6", roles: ["analyst","manager","admin"] },
  { label: "View All Cases",         icon: Eye,          to: "/cases",                         roles: ["analyst","manager","admin"] },

  // ── Governance ───────────────────────────────────────────────────────
  { label: "Analyst Review Queue",   icon: Eye,          to: "/analyst",   accent: "#7c3aed", roles: ["analyst","admin"],  divider: true },
  { label: "Manager Approval Queue", icon: CheckCircle2, to: "/manager",   accent: "#d97706", roles: ["manager","admin"] },
  { label: "Execute Recovery",       icon: Zap,          to: "/execute",   accent: "#059669", roles: ["manager","admin"] },
  { label: "Governance Tokens",      icon: ShieldCheck,  to: "/execute",                      roles: ["manager","admin"] },

  // ── Reports / Analytics ──────────────────────────────────────────────
  { label: "Performance Dashboard",  icon: BarChart3,    to: "/performance",                  roles: ["analyst","manager","admin"], divider: true },
  { label: "Audit & ACR Reports",    icon: FileText,     to: "/crypto",                       roles: ["analyst","manager","admin"] },

  // ── Admin ────────────────────────────────────────────────────────────
  { label: "User Management",        icon: Users,        to: "/users",                         roles: ["admin"], divider: true },
];

interface Props { isDark: boolean; role: string; }

export default function ActionsMenu({ isDark, role }: Props) {
  const nav = useNavigate();
  const [open, setOpen]     = useState(false);
  const [cursor, setCursor] = useState(-1);
  const ref                 = useRef<HTMLDivElement>(null);

  const visible = ACTIONS.filter(a => a.roles.includes(role));

  useEffect(() => {
    function handle(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false); setCursor(-1);
      }
    }
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, []);

  function handleKey(e: React.KeyboardEvent) {
    const items = visible.filter(a => !a.divider);
    if (e.key === "ArrowDown") { e.preventDefault(); setCursor(c => Math.min(c + 1, items.length - 1)); }
    if (e.key === "ArrowUp")   { e.preventDefault(); setCursor(c => Math.max(c - 1, 0)); }
    if (e.key === "Escape")    { setOpen(false); setCursor(-1); }
    if (e.key === "Enter" && cursor >= 0 && items[cursor]?.to) {
      nav(items[cursor].to!); setOpen(false);
    }
  }

  // Theme
  const bg     = isDark ? "#0d1424" : "#ffffff";
  const border = isDark ? "#1e293b" : "#e2e8f0";
  const text   = isDark ? "#e2e8f0" : "#1e293b";
  const muted  = isDark ? "#475569" : "#94a3b8";
  const hover  = isDark ? "#0d1a2e" : "#f8fafc";
  const divBg  = isDark ? "#0a0f1e" : "#f1f5f9";
  const btnBg  = isDark ? "#1e293b" : "#f8fafc";
  const btnBrd = isDark ? "#334155" : "#e2e8f0";

  let itemIdx = -1; // track non-divider index for cursor matching

  return (
    <div ref={ref} style={{ position: "relative" }} onKeyDown={handleKey}>
      {/* Trigger */}
      <button
        onClick={() => { setOpen(o => !o); setCursor(-1); }}
        style={{
          display: "flex", alignItems: "center", gap: 5,
          padding: "6px 12px", background: btnBg,
          border: `1px solid ${btnBrd}`, borderRadius: 8,
          fontSize: 12, fontWeight: 600, color: text,
          cursor: "pointer", transition: "background 0.15s",
        }}
      >
        Actions
        <ChevronDown style={{ width: 12, height: 12, color: muted, transform: open ? "rotate(180deg)" : "none", transition: "transform 0.15s" }} />
      </button>

      {/* Dropdown */}
      {open && (
        <div style={{
          position: "absolute", top: "calc(100% + 6px)", right: 0, zIndex: 9999,
          background: bg, border: `1px solid ${border}`, borderRadius: 10,
          boxShadow: isDark ? "0 8px 32px rgba(0,0,0,0.6)" : "0 8px 32px rgba(0,0,0,0.12)",
          width: 230, overflow: "hidden",
        }}>

          {/* Header */}
          <div style={{ padding: "8px 14px 6px", fontSize: 10, fontWeight: 700, color: muted, textTransform: "uppercase", letterSpacing: "0.08em", background: divBg, borderBottom: `1px solid ${border}` }}>
            Quick Actions
          </div>

          {visible.map((action, i) => {
            if (action.divider && i > 0) {
              // render divider then the item
              return (
                <div key={action.label + "-grp"}>
                  <div style={{ height: 1, background: border }} />
                  <ActionItem action={action} isDark={isDark} text={text} muted={muted} hover={hover}
                    active={++itemIdx === cursor} onSelect={() => { if (action.to) { nav(action.to); } setOpen(false); }} />
                </div>
              );
            }
            const isActive = ++itemIdx === cursor;
            return (
              <ActionItem key={action.label} action={action} isDark={isDark} text={text} muted={muted}
                hover={hover} active={isActive}
                onSelect={() => { if (action.to) { nav(action.to); } if (action.onClick) action.onClick(); setOpen(false); }} />
            );
          })}

          {/* Footer */}
          <div style={{ borderTop: `1px solid ${border}`, padding: "8px 14px", background: divBg }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <RefreshCw style={{ width: 11, height: 11, color: muted }} />
              <span style={{ fontSize: 10, color: muted }}>↑↓ navigate · ↵ open · Esc close</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ActionItem({ action, isDark, text, muted, hover, active, onSelect }: {
  action: Action; isDark: boolean; text: string; muted: string; hover: string; active: boolean;
  onSelect: () => void;
}) {
  const Icon = action.icon;
  return (
    <div
      onClick={onSelect}
      style={{
        display: "flex", alignItems: "center", gap: 10,
        padding: "9px 14px", cursor: "pointer",
        background: active ? hover : "transparent",
        transition: "background 0.1s",
      }}
      onMouseEnter={e => (e.currentTarget.style.background = hover)}
      onMouseLeave={e => (e.currentTarget.style.background = active ? hover : "transparent")}
    >
      <div style={{
        width: 28, height: 28, borderRadius: 7, flexShrink: 0,
        background: action.accent ? action.accent + "18" : (isDark ? "#1e293b" : "#f1f5f9"),
        display: "flex", alignItems: "center", justifyContent: "center",
      }}>
        <Icon style={{ width: 13, height: 13, color: action.accent || muted }} />
      </div>
      <span style={{ fontSize: 13, color: text, fontWeight: 500 }}>{action.label}</span>
    </div>
  );
}
