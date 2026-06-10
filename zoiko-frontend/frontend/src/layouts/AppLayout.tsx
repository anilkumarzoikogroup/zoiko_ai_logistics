import { NavLink, Outlet, useNavigate, useLocation } from "react-router-dom";
import { useAppDispatch, useAppSelector } from "@/store";
import { logout as logoutAction } from "@/store/authSlice";
import { queryClient } from "@/lib/queryClient";
import { zoikoApi } from "@/api/zoiko";
import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import { cn } from "@/utils/cn";
import {
  LayoutDashboard, FileText, Upload, MessageSquare,
  FileCheck, BarChart2, Settings,
  Users, Database, Building2, Bell, Plug,
  Truck, ClipboardList, ShieldCheck, Lock,
  PanelLeftClose, PanelLeftOpen, LogOut,
} from "lucide-react";
import { useState } from "react";

type NavItem = { label: string; icon: React.ElementType; to: string; end?: boolean };

// ── Main workflow ─────────────────────────────────────────────────────────────
const MAIN_NAV: NavItem[] = [
  { label: "Dashboard",      icon: LayoutDashboard, to: "/",            end: true },
  { label: "Invoices",       icon: FileText,        to: "/cases"                  },
  { label: "Upload Invoice", icon: Upload,          to: "/cases/new"              },
  { label: "Disputes",       icon: MessageSquare,   to: "/disputes"               },
  { label: "Contracts",      icon: FileCheck,       to: "/rate-control"           },
  { label: "Carriers",       icon: Truck,           to: "/carriers"               },
  { label: "Connectors",     icon: Plug,            to: "/connectors"             },
  { label: "Analytics",      icon: BarChart2,       to: "/analytics"              },
  { label: "Settings",       icon: Settings,        to: "/settings"               },
];

// ── Compliance & audit ────────────────────────────────────────────────────────
const COMPLIANCE_NAV: NavItem[] = [
  { label: "Audit Trail",   icon: ClipboardList, to: "/alerts"   },
  { label: "ACR Verifier",  icon: ShieldCheck,   to: "/verifier" },
  { label: "Crypto Proofs", icon: Lock,          to: "/crypto"   },
];

// ── Admin only ────────────────────────────────────────────────────────────────
const ADMIN_NAV: NavItem[] = [
  { label: "Team",               icon: Users,     to: "/users"               },
  { label: "DB Stats",           icon: Database,  to: "/database"            },
  { label: "Workspace Requests", icon: Building2, to: "/workspace-requests"  },
];

const TITLE_MAP: Record<string, string> = {
  "/":                   "Dashboard",
  "/cases":              "Invoices",
  "/cases/new":          "Upload Invoice",
  "/disputes":           "Disputes",
  "/rate-control":       "Contracts",
  "/analytics":          "Analytics",
  "/settings":           "Settings",
  "/billing":            "Billing",
  "/referrals":          "Referrals",
  "/carriers":           "Carriers",
  "/connectors":         "Connectors",
  "/users":              "Team",
  "/database":           "DB Stats",
  "/workspace-requests": "Workspace Requests",
  "/alerts":             "Audit Trail",
  "/verifier":           "ACR Verifier",
  "/crypto":             "Crypto",
};

function SideNavItem({ item, collapsed }: { item: NavItem; collapsed: boolean }) {
  const Icon = item.icon;
  return (
    <NavLink to={item.to} end={item.end} title={collapsed ? item.label : undefined}>
      {({ isActive }) => (
        <span className={cn(
          "flex items-center gap-3 rounded-lg text-[13px] font-medium transition-all duration-150 cursor-pointer select-none",
          collapsed ? "justify-center p-2.5" : "px-3 py-2.5",
          isActive
            ? "bg-[#1a2f47] text-white"
            : "text-[#8fa3b8] hover:bg-[#162638] hover:text-white"
        )}>
          <Icon className={cn("h-[15px] w-[15px] flex-shrink-0", isActive ? "text-[#f59e0b]" : "")} />
          {!collapsed && <span className="truncate leading-none">{item.label}</span>}
        </span>
      )}
    </NavLink>
  );
}

export default function AppLayout() {
  const location  = useLocation();
  const nav       = useNavigate();
  const dispatch  = useAppDispatch();
  const user      = useAppSelector(s => s.auth.user) || "User";
  const role      = useAppSelector(s => s.auth.role) || "analyst";
  const [collapsed, setCollapsed] = useState(false);

  const { data: cases = [] } = useQuery({
    queryKey: ["cases"],
    queryFn: () => zoikoApi.listCases(),
    refetchInterval: 10000,
  });

  const pendingCount = (cases as any[]).filter((c: any) =>
    ["FINDING_GENERATED", "APPROVAL_PENDING", "EXECUTION_READY"].includes(c.state)
  ).length;

  const path  = location.pathname;
  const title = TITLE_MAP[path] ?? (path.startsWith("/cases/") ? "Invoice Details" : "Zoiko");

  function handleLogout() {
    axios.post("/api/v1/auth/signout", {}, { withCredentials: true }).catch(() => {});
    dispatch(logoutAction());
    queryClient.clear();
    nav("/login");
  }

  const initials = (user || "U")
    .split(" ")
    .map((w: string) => w[0] || "")
    .join("")
    .slice(0, 2)
    .toUpperCase() || "U";

  const showAdmin = role === "admin";

  function NavSection({ label, items }: { label: string; items: NavItem[] }) {
    return (
      <>
        <div className={cn("pt-3 pb-1", !collapsed && "px-3")}>
          {!collapsed
            ? <p className="text-[9px] font-bold uppercase tracking-[0.12em] text-[#3a5060] select-none">{label}</p>
            : <div className="h-px bg-white/5" />
          }
        </div>
        {items.map(item => (
          <SideNavItem key={item.to} item={item} collapsed={collapsed} />
        ))}
      </>
    );
  }

  return (
    <div className="flex h-screen bg-[#f0f3f8] overflow-hidden">

      {/* ── Sidebar ─────────────────────────────────────────────────────────── */}
      <aside className={cn(
        "relative flex flex-col flex-shrink-0 transition-all duration-200 bg-[#0d1b2e]",
        collapsed ? "w-[60px]" : "w-[240px]",
      )}>

        {/* Logo */}
        <div className={cn(
          "flex items-center h-[56px] border-b border-white/5 flex-shrink-0",
          collapsed ? "justify-center" : "px-4 gap-3",
        )}>
          <div className="h-[34px] w-[34px] rounded-lg overflow-hidden flex-shrink-0 bg-[#f59e0b] flex items-center justify-center">
            <img
              src="/logo-dark.jpg"
              alt="Zoiko"
              className="h-full w-full object-cover"
              onError={e => { (e.currentTarget as HTMLImageElement).style.display = "none"; }}
            />
          </div>
          {!collapsed && (
            <div>
              <p className="text-white font-black text-[14px] leading-tight tracking-tight">Zoiko.ai</p>
              <p className="text-[#4a6480] text-[10px] leading-tight">Freight Auditing</p>
            </div>
          )}
        </div>

        {/* Collapse toggle — below logo */}
        <div className={cn(
          "flex border-b border-white/5 flex-shrink-0",
          collapsed ? "justify-center px-2 py-2" : "px-3 py-2",
        )}>
          <button
            onClick={() => setCollapsed(c => !c)}
            className="flex items-center gap-2 rounded-md text-[#4a6480] hover:text-[#8fa3b8] hover:bg-white/5 transition-colors p-1.5"
          >
            {collapsed
              ? <PanelLeftOpen  className="h-3.5 w-3.5" />
              : <><PanelLeftClose className="h-3.5 w-3.5" /><span className="text-[11px]">Collapse</span></>
            }
          </button>
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto py-2 px-2 space-y-0.5 scrollbar-none">
          {MAIN_NAV.map(item => (
            <SideNavItem key={item.to} item={item} collapsed={collapsed} />
          ))}

          <NavSection label="Compliance" items={COMPLIANCE_NAV} />

          {showAdmin && (
            <NavSection label="Admin" items={ADMIN_NAV} />
          )}
        </nav>

        {/* User footer */}
        <div className="border-t border-white/5 p-2 flex-shrink-0">
          {collapsed ? (
            <div className="flex flex-col items-center gap-1">
              <div className="h-8 w-8 rounded-full bg-[#f59e0b] flex items-center justify-center text-[#0d1b2e] text-[11px] font-black">
                {initials}
              </div>
              <button onClick={handleLogout} title="Sign out" className="p-1.5 rounded text-[#4a6480] hover:text-red-400 transition-colors">
                <LogOut className="h-3.5 w-3.5" />
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2.5 px-2 py-2 rounded-lg group">
              <div className="h-8 w-8 rounded-full bg-[#f59e0b] flex items-center justify-center text-[#0d1b2e] text-[11px] font-black flex-shrink-0">
                {initials}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-[12px] font-semibold text-white truncate leading-tight">{user}</p>
                <p className="text-[10px] text-[#4a6480] capitalize leading-tight">{role}</p>
              </div>
              <button onClick={handleLogout} title="Sign out" className="text-[#4a6480] hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100">
                <LogOut className="h-3.5 w-3.5" />
              </button>
            </div>
          )}
        </div>
      </aside>

      {/* ── Main ────────────────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col overflow-hidden">

        {/* Topbar */}
        <header className="h-[52px] bg-white border-b border-[#e8edf2] flex items-center px-5 flex-shrink-0">
          <div className="flex items-center gap-2.5 flex-1">
            <div className="h-6 w-6 rounded border border-[#e8edf2] flex items-center justify-center flex-shrink-0">
              <svg className="h-3 w-3 text-slate-400" fill="none" viewBox="0 0 12 12">
                <rect x="1" y="1" width="4" height="4" rx="0.5" fill="currentColor" />
                <rect x="7" y="1" width="4" height="4" rx="0.5" fill="currentColor" />
                <rect x="1" y="7" width="4" height="4" rx="0.5" fill="currentColor" />
                <rect x="7" y="7" width="4" height="4" rx="0.5" fill="currentColor" />
              </svg>
            </div>
            <h1 className="text-[14px] font-semibold text-slate-700">{title}</h1>
          </div>

          <button
            onClick={() => nav("/cases")}
            className="relative p-2 rounded-lg hover:bg-slate-50 transition-colors"
            title={pendingCount > 0 ? `${pendingCount} pending actions` : "Notifications"}
          >
            <Bell className="h-[18px] w-[18px] text-slate-500" />
            {pendingCount > 0 && (
              <span className="absolute top-1.5 right-1.5 h-3.5 w-3.5 bg-red-500 rounded-full text-[8px] text-white flex items-center justify-center font-bold leading-none">
                {pendingCount > 9 ? "9+" : pendingCount}
              </span>
            )}
          </button>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto bg-[#f0f3f8]">
          <div className="px-6 py-5 max-w-[1440px] mx-auto">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
