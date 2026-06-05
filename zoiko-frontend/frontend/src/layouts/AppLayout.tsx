import { NavLink, Outlet, useNavigate, useLocation } from "react-router-dom";
import { useAppDispatch, useAppSelector } from "@/store";
import { logout as logoutAction } from "@/store/authSlice";
import { queryClient } from "@/lib/queryClient";
import { cn } from "@/utils/cn";
import {
  LayoutDashboard, FileText, FolderOpen,
  FileClock, Truck, ShieldCheck, BookOpen,
  Key, Archive, ClipboardList,
  BarChart3, TrendingUp,
  Users, Settings, Building2, Bell, Search,
  ChevronLeft, ChevronRight, LogOut, Calendar, ChevronDown,
  Download, Zap, CheckSquare, FlaskConical,
} from "lucide-react";
import { useState } from "react";

const ROLE_COLORS: Record<string, string> = {
  analyst: "from-blue-500 to-blue-700",
  manager: "from-violet-500 to-purple-700",
  admin:   "from-slate-500 to-slate-700",
};

type NavEntry = { label: string; icon: React.ElementType; to: string; badge?: string; roles?: string[] };
type NavGroup = { group: string; roles?: string[]; items: NavEntry[] };

const NAV: NavGroup[] = [
  {
    group: "OPERATIONS",
    items: [
      { label: "Dashboard",        icon: LayoutDashboard, to: "/"                  },
      { label: "Invoices & Cases", icon: FolderOpen,      to: "/cases"             },
      { label: "Submit Invoice",   icon: FileText,        to: "/cases/new"         },
      { label: "Audit Conditions", icon: CheckSquare,     to: "/audit-conditions"  },
      { label: "Contracts & Rates",icon: FileClock,       to: "/rate-control"      },
      { label: "Carriers",         icon: Truck,           to: "/carriers"          },
    ],
  },
  {
    group: "GOVERNANCE",
    items: [
      { label: "Analyst Review",   icon: BookOpen,     to: "/analyst", roles: ["analyst","admin"]         },
      { label: "Manager Approval", icon: ShieldCheck,  to: "/manager", roles: ["manager","admin"]         },
      { label: "Execute Recovery", icon: Zap,          to: "/execute", roles: ["manager","admin"]         },
      { label: "Gov. Tokens",      icon: Key,          to: "/execute", roles: ["manager","admin"]         },
      { label: "Audit & ACR",      icon: Archive,      to: "/crypto"                                      },
      { label: "ACR Verifier",     icon: ShieldCheck,  to: "/verifier"                                    },
      { label: "Audit Trail",      icon: ClipboardList,to: "/alerts"                                      },
    ],
  },
  {
    group: "ANALYTICS",
    items: [
      { label: "Performance", icon: BarChart3,  to: "/performance" },
      { label: "Analytics",   icon: TrendingUp, to: "/analytics"   },
    ],
  },
  {
    group: "ADMIN",
    roles: ["admin"],
    items: [
      { label: "Tenants",         icon: Building2,    to: "/tenants"             },
      { label: "Signup Requests", icon: Users,        to: "/workspace-requests", badge: "NEW" },
      { label: "Users & Roles",   icon: Users,        to: "/users"               },
      { label: "DB Stats",      icon: Building2,    to: "/database" },
      { label: "Settings",      icon: Settings,     to: "/settings" },
      { label: "Stub Viewer",   icon: FlaskConical, to: "/stubs", badge: "DEV" },
    ],
  },
];

function NavItem({ to, label, icon: Icon, collapsed, badge }: {
  to: string; label: string; icon: React.ElementType; collapsed: boolean; badge?: string; roles?: string[];
}) {
  return (
    <NavLink
      to={to}
      end={to === "/"}
      title={collapsed ? label : undefined}
      className={({ isActive }) => cn(
        "flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px] transition-all duration-150 relative",
        collapsed ? "justify-center px-2" : "",
        isActive
          ? "bg-blue-600 text-white font-semibold shadow-sm shadow-blue-500/40"
          : "text-slate-400 hover:bg-slate-700/60 hover:text-slate-200"
      )}
    >
      <Icon className="h-4 w-4 flex-shrink-0" />
      {!collapsed && <span className="truncate flex-1">{label}</span>}
      {!collapsed && badge && (
        <span className="ml-auto text-[9px] font-bold bg-blue-500/20 text-blue-300 px-1.5 py-0.5 rounded-full">
          {badge}
        </span>
      )}
    </NavLink>
  );
}

export default function AppLayout() {
  const nav      = useNavigate();
  const location = useLocation();
  const dispatch = useAppDispatch();
  const user     = useAppSelector(s => s.auth.user)  || "User";
  const role     = useAppSelector(s => s.auth.role)  || "analyst"; // default to least-privilege
  const [collapsed, setCollapsed] = useState(false);

  // Derive page title from current path (use all items regardless of role for title lookup)
  const allItems = NAV.flatMap(g => g.items);
  const activeItem = allItems.find(item =>
    item.to === "/" ? location.pathname === "/" : location.pathname.startsWith(item.to)
  );
  const pageTitle = activeItem?.label ?? "Dashboard";

  function handleLogout() {
    dispatch(logoutAction());
    queryClient.clear();
    nav("/login");
  }

  const initials = (user || "U").split(" ").map((w: string) => w[0] || "").join("").slice(0, 2).toUpperCase() || "U";

  return (
    <div className="flex h-screen bg-slate-100 overflow-hidden">

      {/* ── Sidebar ─────────────────────────────────────────────────────── */}
      <aside className={cn(
        "flex flex-col border-r border-slate-700/40 transition-all duration-200 flex-shrink-0 relative",
        "bg-[#0d1424]",
        collapsed ? "w-[60px]" : "w-[220px]"
      )}>
        {/* Subtle top gradient accent */}
        <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-blue-600 via-blue-500 to-cyan-500 rounded-tl-none rounded-tr-none" />

        {/* Logo */}
        <div className={cn(
          "flex items-center justify-center px-4 py-4 border-b border-slate-700/40 flex-shrink-0",
          collapsed ? "px-2" : "px-3"
        )}>
          {collapsed ? (
            /* Icon-only when collapsed */
            <img
              src="/logo-icon.svg"
              alt="Z"
              className="h-8 w-8 object-contain"
              onError={e => {
                const t = e.currentTarget;
                t.style.display = "none";
                const fb = t.nextElementSibling as HTMLElement | null;
                if (fb) fb.style.display = "flex";
              }}
            />
          ) : (
            /* Full logo when expanded */
            <img
              src="/logo-dark.jpg"
              alt="ZoikoAI"
              className="h-10 w-auto object-contain"
              onError={e => {
                const t = e.currentTarget;
                t.style.display = "none";
                const fb = t.nextElementSibling as HTMLElement | null;
                if (fb) fb.style.display = "flex";
              }}
            />
          )}
          {/* Fallback text logo */}
          <div className="hidden items-center gap-2">
            <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-blue-500 to-blue-700 flex items-center justify-center text-white font-bold text-sm flex-shrink-0">
              Z
            </div>
            {!collapsed && (
              <div>
                <p className="font-bold text-white text-sm leading-tight">ZOIKO</p>
                <div className="flex items-center gap-1 mt-0.5">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  <p className="text-[9px] text-slate-500 uppercase tracking-widest">Live</p>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto py-3 space-y-4 px-2 scrollbar-thin">
          {NAV.filter(g => !g.roles || g.roles.includes(role)).map(({ group, items }) => {
            const visibleItems = items.filter(i => !i.roles || i.roles.includes(role));
            if (visibleItems.length === 0) return null;
            return (
              <div key={group}>
                {!collapsed && (
                  <p className="px-3 mb-1.5 text-[9px] font-bold tracking-widest text-slate-600 uppercase">
                    {group}
                  </p>
                )}
                {collapsed && <div className="h-px bg-slate-700/40 mx-2 mb-2 mt-1" />}
                <div className="space-y-0.5">
                  {visibleItems.map(item => (
                    <NavItem
                      key={item.label + item.to}
                      to={item.to}
                      label={item.label}
                      icon={item.icon}
                      collapsed={collapsed}
                      badge={item.badge}
                    />
                  ))}
                </div>
              </div>
            );
          })}
        </nav>

        {/* Footer: user + collapse */}
        <div className="border-t border-slate-700/40 px-2 py-3 space-y-1 flex-shrink-0">
          {!collapsed && (
            <div className="flex items-center gap-2 px-3 py-2 mb-1 rounded-lg hover:bg-slate-700/40 transition-colors">
              <div className={cn(
                "h-7 w-7 rounded-full bg-gradient-to-br flex items-center justify-center text-white text-[11px] font-bold flex-shrink-0",
                ROLE_COLORS[role] || "from-slate-500 to-slate-700"
              )}>
                {initials}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-semibold text-white truncate">{user}</p>
                <p className="text-[10px] text-slate-500 capitalize">{role}</p>
              </div>
              <button
                onClick={handleLogout}
                title="Sign out"
                className="text-slate-600 hover:text-red-400 transition-colors ml-1"
              >
                <LogOut className="h-3.5 w-3.5" />
              </button>
            </div>
          )}
          <button
            onClick={() => setCollapsed(c => !c)}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className="flex items-center gap-2 w-full px-3 py-2 rounded-lg text-slate-500 hover:bg-slate-700/40 hover:text-slate-300 transition-colors text-[12px]"
          >
            {collapsed
              ? <ChevronRight className="h-4 w-4 mx-auto" />
              : <><ChevronLeft className="h-4 w-4" /><span>Collapse</span></>
            }
          </button>
        </div>
      </aside>

      {/* ── Main ────────────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col overflow-hidden">

        {/* Top bar */}
        <header className="h-[56px] bg-white border-b border-slate-200 flex items-center gap-4 px-5 flex-shrink-0 shadow-sm">

          {/* Page title (mobile) */}
          <div className="font-semibold text-slate-700 text-sm hidden sm:block">
            {pageTitle}
          </div>

          <div className="flex-1 flex items-center gap-3">
            <div className="relative">
              <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                placeholder="Search invoices, cases, carriers…"
                className="pl-9 pr-10 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-600 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/30 w-64 transition-all focus:w-80"
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-slate-400 font-mono bg-slate-100 px-1 rounded">⌘K</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Date range */}
            <button className="hidden md:flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 text-xs text-slate-600 hover:bg-slate-50 transition-colors">
              <Calendar className="h-3.5 w-3.5 text-slate-400" />
              <span>Jul 2025</span>
            </button>

            {/* Actions */}
            <button className="hidden md:flex items-center gap-1 px-3 py-1.5 rounded-lg border border-slate-200 text-xs text-slate-600 hover:bg-slate-50 transition-colors">
              Actions <ChevronDown className="h-3 w-3 text-slate-400" />
            </button>

            {/* Export */}
            <button className="hidden md:flex items-center gap-1 px-3 py-1.5 rounded-lg border border-slate-200 text-xs text-slate-600 hover:bg-slate-50 transition-colors">
              <Download className="h-3.5 w-3.5" /> Export
            </button>

            {/* Notifications */}
            <button className="relative p-2 rounded-lg hover:bg-slate-50 transition-colors">
              <Bell className="h-4 w-4 text-slate-500" />
              <span className="absolute top-1 right-1 h-3.5 w-3.5 bg-red-500 rounded-full text-[8px] text-white flex items-center justify-center font-bold">3</span>
            </button>

            {/* User pill */}
            <div className="flex items-center gap-2 pl-2 border-l border-slate-200">
              <div className={cn(
                "h-7 w-7 rounded-full bg-gradient-to-br flex items-center justify-center text-white text-[11px] font-bold",
                ROLE_COLORS[role] || "from-slate-500 to-slate-700"
              )}>
                {initials}
              </div>
              <div className="hidden lg:block">
                <p className="text-xs font-semibold text-slate-700 leading-tight">{user}</p>
                <span style={{
                  fontSize: 9, fontWeight: 700, padding: "1px 6px", borderRadius: 99,
                  background: role==="admin" ? "#1e3a8a" : role==="manager" ? "#4c1d95" : "#064e3b",
                  color: "#fff", textTransform: "uppercase", letterSpacing: "0.06em",
                }}>
                  {role}
                </span>
              </div>
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto bg-slate-50">
          <div className="px-6 py-5 max-w-[1600px] mx-auto">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
