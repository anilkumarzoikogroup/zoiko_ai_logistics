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
  Download, Zap, CheckSquare, FlaskConical, Sun, Moon,
} from "lucide-react";
import { useState } from "react";
import { useTheme } from "@/hooks/useTheme";
import ZoikoLogo from "@/components/ZoikoLogo";

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
      { label: "Dashboard",         icon: LayoutDashboard, to: "/"                 },
      { label: "Invoices & Cases",  icon: FolderOpen,      to: "/cases"            },
      { label: "Submit Invoice",    icon: FileText,        to: "/cases/new"        },
      { label: "Audit Conditions",  icon: CheckSquare,     to: "/audit-conditions" },
      { label: "Contracts & Rates", icon: FileClock,       to: "/rate-control"     },
      { label: "Carriers",          icon: Truck,           to: "/payment-control"  },
    ],
  },
  {
    group: "GOVERNANCE",
    items: [
      { label: "Analyst Review",   icon: BookOpen,     to: "/analyst", roles: ["analyst","admin"]  },
      { label: "Manager Approval", icon: ShieldCheck,  to: "/manager", roles: ["manager","admin"]  },
      { label: "Execute Recovery", icon: Zap,          to: "/execute", roles: ["manager","admin"]  },
      { label: "Gov. Tokens",      icon: Key,          to: "/execute", roles: ["manager","admin"]  },
      { label: "Audit & ACR",      icon: Archive,      to: "/crypto"                               },
      { label: "ACR Verifier",     icon: ShieldCheck,  to: "/verifier"                             },
      { label: "Audit Trail",      icon: ClipboardList,to: "/alerts"                               },
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
      { label: "Tenants",       icon: Building2,    to: "/tenants"  },
      { label: "Users & Roles", icon: Users,        to: "/users"    },
      { label: "DB Stats",      icon: Building2,    to: "/database" },
      { label: "Settings",      icon: Settings,     to: "/settings" },
      { label: "Stub Viewer",   icon: FlaskConical, to: "/stubs", badge: "DEV" },
    ],
  },
];

function NavItem({
  to, label, icon: Icon, collapsed, badge, theme,
}: {
  to: string; label: string; icon: React.ElementType;
  collapsed: boolean; badge?: string; theme: "light" | "dark";
}) {
  const isDark = theme === "dark";
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
          : isDark
            ? "text-slate-400 hover:bg-slate-700/60 hover:text-slate-200"
            : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
      )}
    >
      <Icon className="h-4 w-4 flex-shrink-0" />
      {!collapsed && <span className="truncate flex-1">{label}</span>}
      {!collapsed && badge && (
        <span className="ml-auto text-[9px] font-bold bg-blue-500/20 text-blue-400 px-1.5 py-0.5 rounded-full">
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
  const user     = useAppSelector(s => s.auth.user) || "User";
  const role     = useAppSelector(s => s.auth.role) || "analyst";
  const [collapsed, setCollapsed] = useState(false);
  const { theme, toggleTheme } = useTheme();
  const isDark = theme === "dark";

  const allItems  = NAV.flatMap(g => g.items);
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

  // ── Theme-aware class sets ─────────────────────────────────────────────────
  const sidebar = isDark
    ? "bg-[#0d1424] border-slate-700/40"
    : "bg-white border-slate-200";

  const topbar = isDark
    ? "bg-[#0d1424] border-slate-700/50 shadow-none"
    : "bg-white border-slate-200 shadow-sm";

  const mainBg = isDark ? "bg-[#0b1020]" : "bg-slate-50";

  const groupLabel = isDark ? "text-slate-600" : "text-slate-400";

  const userPill  = isDark
    ? "text-slate-200 hover:bg-slate-700/60"
    : "text-slate-700 hover:bg-slate-100";

  const divider = isDark ? "border-slate-700/40" : "border-slate-200";

  const searchBox = isDark
    ? "bg-slate-800 border-slate-700 text-slate-300 placeholder:text-slate-500 focus:ring-blue-500/30"
    : "bg-slate-50 border-slate-200 text-slate-600 placeholder:text-slate-400 focus:ring-blue-500/30";

  const headerBtn = isDark
    ? "border-slate-700 text-slate-400 hover:bg-slate-700/60"
    : "border-slate-200 text-slate-600 hover:bg-slate-50";

  const collapseBtn = isDark
    ? "text-slate-500 hover:bg-slate-700/40 hover:text-slate-300"
    : "text-slate-500 hover:bg-slate-100 hover:text-slate-700";

  const accentBar = "from-blue-600 via-blue-500 to-cyan-500";

  return (
    <div className={cn("flex h-screen overflow-hidden transition-colors duration-200", isDark ? "bg-[#0b1020]" : "bg-slate-100")}>

      {/* ── Sidebar ──────────────────────────────────────────────────────── */}
      <aside className={cn(
        "flex flex-col border-r transition-all duration-200 flex-shrink-0 relative",
        sidebar,
        collapsed ? "w-[60px]" : "w-[220px]"
      )}>
        {/* Top accent strip */}
        <div className={cn("absolute top-0 left-0 right-0 h-0.5 bg-gradient-to-r", accentBar)} />

        {/* Logo block */}
        <div className={cn(
          "flex items-center border-b py-4 flex-shrink-0",
          divider,
          collapsed ? "justify-center px-2" : "px-4"
        )}>
          <ZoikoLogo
            theme={theme}
            size={collapsed ? 36 : 38}
            showText={!collapsed}
            collapsed={collapsed}
          />
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto py-3 space-y-4 px-2 scrollbar-thin">
          {NAV.filter(g => !g.roles || g.roles.includes(role)).map(({ group, items }) => {
            const visible = items.filter(i => !i.roles || i.roles.includes(role));
            if (!visible.length) return null;
            return (
              <div key={group}>
                {!collapsed && (
                  <p className={cn("px-3 mb-1.5 text-[9px] font-bold tracking-widest uppercase", groupLabel)}>
                    {group}
                  </p>
                )}
                {collapsed && <div className={cn("h-px mx-2 mb-2 mt-1", isDark ? "bg-slate-700/40" : "bg-slate-200")} />}
                <div className="space-y-0.5">
                  {visible.map(item => (
                    <NavItem
                      key={item.label + item.to}
                      to={item.to}
                      label={item.label}
                      icon={item.icon}
                      collapsed={collapsed}
                      badge={item.badge}
                      theme={theme}
                    />
                  ))}
                </div>
              </div>
            );
          })}
        </nav>

        {/* Sidebar footer */}
        <div className={cn("border-t px-2 py-3 space-y-1 flex-shrink-0", divider)}>
          {!collapsed && (
            <div className={cn("flex items-center gap-2 px-3 py-2 mb-1 rounded-lg transition-colors cursor-default", userPill)}>
              <div className={cn(
                "h-7 w-7 rounded-full bg-gradient-to-br flex items-center justify-center text-white text-[11px] font-bold flex-shrink-0",
                ROLE_COLORS[role] || "from-slate-500 to-slate-700"
              )}>
                {initials}
              </div>
              <div className="flex-1 min-w-0">
                <p className={cn("text-xs font-semibold truncate", isDark ? "text-white" : "text-slate-800")}>{user}</p>
                <p className={cn("text-[10px] capitalize", isDark ? "text-slate-500" : "text-slate-400")}>{role}</p>
              </div>
              <button
                onClick={handleLogout}
                title="Sign out"
                className={cn("transition-colors ml-1", isDark ? "text-slate-600 hover:text-red-400" : "text-slate-400 hover:text-red-500")}
              >
                <LogOut className="h-3.5 w-3.5" />
              </button>
            </div>
          )}
          <button
            onClick={() => setCollapsed(c => !c)}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className={cn("flex items-center gap-2 w-full px-3 py-2 rounded-lg transition-colors text-[12px]", collapseBtn)}
          >
            {collapsed
              ? <ChevronRight className="h-4 w-4 mx-auto" />
              : <><ChevronLeft className="h-4 w-4" /><span>Collapse</span></>
            }
          </button>
        </div>
      </aside>

      {/* ── Main area ────────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col overflow-hidden">

        {/* Top bar */}
        <header className={cn(
          "h-[56px] flex items-center gap-4 px-5 flex-shrink-0 border-b transition-colors duration-200",
          topbar
        )}>
          {/* Page title */}
          <div className={cn("font-semibold text-sm hidden sm:block", isDark ? "text-slate-300" : "text-slate-700")}>
            {pageTitle}
          </div>

          <div className="flex-1 flex items-center gap-3">
            <div className="relative">
              <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                placeholder="Search invoices, cases, carriers…"
                className={cn(
                  "pl-9 pr-10 py-1.5 border rounded-lg text-sm focus:outline-none focus:ring-2 w-64 transition-all focus:w-80",
                  searchBox
                )}
              />
              <span className={cn(
                "absolute right-3 top-1/2 -translate-y-1/2 text-[10px] font-mono px-1 rounded",
                isDark ? "text-slate-500 bg-slate-700" : "text-slate-400 bg-slate-100"
              )}>⌘K</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Date range */}
            <button className={cn(
              "hidden md:flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs transition-colors",
              headerBtn
            )}>
              <Calendar className="h-3.5 w-3.5 text-slate-400" />
              <span>Jul 2025</span>
            </button>

            {/* Actions */}
            <button className={cn(
              "hidden md:flex items-center gap-1 px-3 py-1.5 rounded-lg border text-xs transition-colors",
              headerBtn
            )}>
              Actions <ChevronDown className="h-3 w-3 text-slate-400" />
            </button>

            {/* Export */}
            <button className={cn(
              "hidden md:flex items-center gap-1 px-3 py-1.5 rounded-lg border text-xs transition-colors",
              headerBtn
            )}>
              <Download className="h-3.5 w-3.5" /> Export
            </button>

            {/* ── Theme toggle ───────────────────────────────────────── */}
            <button
              onClick={toggleTheme}
              title={isDark ? "Switch to light mode" : "Switch to dark mode"}
              className={cn(
                "relative p-2 rounded-lg border transition-all duration-200 group",
                isDark
                  ? "border-slate-700 hover:bg-slate-700/60 text-amber-400"
                  : "border-slate-200 hover:bg-slate-100 text-slate-500"
              )}
            >
              {isDark
                ? <Sun  className="h-4 w-4 transition-transform group-hover:rotate-12" />
                : <Moon className="h-4 w-4 transition-transform group-hover:-rotate-12" />
              }
            </button>

            {/* Notifications */}
            <button className={cn(
              "relative p-2 rounded-lg transition-colors",
              isDark ? "hover:bg-slate-700/60" : "hover:bg-slate-50"
            )}>
              <Bell className={cn("h-4 w-4", isDark ? "text-slate-400" : "text-slate-500")} />
              <span className="absolute top-1 right-1 h-3.5 w-3.5 bg-red-500 rounded-full text-[8px] text-white flex items-center justify-center font-bold">3</span>
            </button>

            {/* User pill */}
            <div className={cn("flex items-center gap-2 pl-2 border-l", divider)}>
              <div className={cn(
                "h-7 w-7 rounded-full bg-gradient-to-br flex items-center justify-center text-white text-[11px] font-bold",
                ROLE_COLORS[role] || "from-slate-500 to-slate-700"
              )}>
                {initials}
              </div>
              <div className="hidden lg:block">
                <p className={cn("text-xs font-semibold leading-tight", isDark ? "text-slate-200" : "text-slate-700")}>{user}</p>
                <span style={{
                  fontSize: 9, fontWeight: 700, padding: "1px 6px", borderRadius: 99,
                  background: role === "admin" ? "#1e3a8a" : role === "manager" ? "#4c1d95" : "#064e3b",
                  color: "#fff", textTransform: "uppercase", letterSpacing: "0.06em",
                }}>
                  {role}
                </span>
              </div>
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className={cn("flex-1 overflow-y-auto transition-colors duration-200", mainBg)}>
          <div className="px-6 py-5 max-w-[1600px] mx-auto">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
