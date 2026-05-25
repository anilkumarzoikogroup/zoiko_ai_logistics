import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { cn } from "@/utils/cn";
import {
  LayoutDashboard, FileText, CheckSquare, FolderOpen,
  FileClock, Truck, Package, ShieldCheck, BookOpen,
  Key, Archive, ClipboardList, CreditCard, RefreshCw,
  Send, BarChart3, TrendingUp, FileBarChart,
  Users, Settings, Building2, Bell, Search, Download,
  ChevronLeft, ChevronRight, LogOut, Calendar, ChevronDown,
} from "lucide-react";
import { useState } from "react";

const ROLE_COLORS: Record<string, string> = {
  analyst: "bg-blue-600",
  manager: "bg-purple-600",
  admin:   "bg-slate-700",
};

type NavEntry = { label: string; icon: React.ElementType; to?: string; children?: NavEntry[] };

const NAV: { group: string; items: NavEntry[] }[] = [
  {
    group: "OPERATIONS",
    items: [
      { label: "Overview",          icon: LayoutDashboard, to: "/"            },
      { label: "Invoices",          icon: FileText,        to: "/invoices"    },
      { label: "Validation",        icon: CheckSquare,     to: "/cases"       },
      { label: "Cases",             icon: FolderOpen,      to: "/cases"       },
      { label: "Contracts & Rates", icon: FileClock,       to: "/rate-control"},
      { label: "Carriers",          icon: Truck,           to: "/audit-conditions" },
      { label: "Shipments",         icon: Package,         to: "/analytics"   },
    ],
  },
  {
    group: "GOVERNANCE",
    items: [
      { label: "Approvals",       icon: ShieldCheck,    to: "/manager"     },
      { label: "Policies",        icon: BookOpen,       to: "/analyst"     },
      { label: "Tokens",          icon: Key,            to: "/execute"     },
      { label: "Evidence & Audit",icon: Archive,        to: "/crypto"      },
      { label: "Audit Trail",     icon: ClipboardList,  to: "/alerts"      },
    ],
  },
  {
    group: "FINANCIALS",
    items: [
      { label: "Recovery & Payments", icon: CreditCard,  to: "/payment-control" },
      { label: "Reconciliation",      icon: RefreshCw,   to: "/payment-control" },
      { label: "Remittances",         icon: Send,        to: "/payment-control" },
      { label: "Statements",          icon: FileText,    to: "/analytics"       },
    ],
  },
  {
    group: "ANALYTICS",
    items: [
      { label: "Performance",   icon: BarChart3,   to: "/performance"   },
      { label: "Savings & ROI", icon: TrendingUp,  to: "/analytics"     },
      { label: "Reports",       icon: FileBarChart,to: "/analytics"     },
    ],
  },
  {
    group: "ADMIN",
    items: [
      { label: "Tenants",      icon: Building2, to: "/database"  },
      { label: "Users & Roles",icon: Users,     to: "/settings"  },
      { label: "Settings",     icon: Settings,  to: "/settings"  },
    ],
  },
];

function NavItem({ to, label, icon: Icon, collapsed }: {
  to: string; label: string; icon: React.ElementType; collapsed: boolean;
}) {
  return (
    <NavLink
      to={to}
      end={to === "/"}
      title={collapsed ? label : undefined}
      className={({ isActive }) => cn(
        "flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px] transition-all duration-150",
        collapsed ? "justify-center px-2" : "",
        isActive
          ? "bg-blue-600 text-white font-semibold shadow-sm"
          : "text-slate-300 hover:bg-slate-700 hover:text-white"
      )}
    >
      <Icon className="h-4 w-4 flex-shrink-0" />
      {!collapsed && <span className="truncate">{label}</span>}
    </NavLink>
  );
}

export default function AppLayout() {
  const nav  = useNavigate();
  const user = localStorage.getItem("zoiko_user") || "Leah Brooks";
  const role     = localStorage.getItem("zoiko_role") || "admin";
  const [collapsed, setCollapsed] = useState(false);

  function handleLogout() {
    localStorage.removeItem("zoiko_role");
    localStorage.removeItem("zoiko_user");
    localStorage.removeItem("zoiko_sub");
    localStorage.removeItem("zoiko_tenant");
    nav("/login");
  }

  return (
    <div className="flex h-screen bg-[#f1f5f9] overflow-hidden">

      {/* ── Sidebar ─────────────────────────────────────────────────────── */}
      <aside className={cn(
        "flex flex-col bg-[#0f172a] border-r border-slate-700/50 transition-all duration-200 flex-shrink-0",
        collapsed ? "w-14" : "w-56"
      )}>

        {/* Logo */}
        <div className={cn("flex items-center gap-2.5 px-4 py-4 border-b border-slate-700/50 flex-shrink-0",
          collapsed && "justify-center px-2")}>
          <div className="h-8 w-8 rounded-lg bg-blue-600 flex items-center justify-center text-white font-bold text-sm flex-shrink-0">Z</div>
          {!collapsed && (
            <div>
              <p className="font-bold text-white text-sm leading-tight">ZOIKO</p>
              <p className="text-[10px] text-slate-400 tracking-wide">Logistics</p>
            </div>
          )}
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto py-3 space-y-4 px-2">
          {NAV.map(({ group, items }) => (
            <div key={group}>
              {!collapsed && (
                <p className="px-3 mb-1 text-[10px] font-semibold tracking-widest text-slate-500 uppercase">
                  {group}
                </p>
              )}
              <div className="space-y-0.5">
                {items.map(item => (
                  <NavItem key={item.label} to={item.to!} label={item.label} icon={item.icon} collapsed={collapsed} />
                ))}
              </div>
            </div>
          ))}
        </nav>

        {/* Collapse toggle + logout */}
        <div className="border-t border-slate-700/50 px-2 py-3 space-y-1 flex-shrink-0">
          {!collapsed && (
            <div className="flex items-center gap-2 px-3 py-2 mb-1">
              <div className={cn("h-7 w-7 rounded-full flex items-center justify-center text-white text-[11px] font-bold flex-shrink-0", ROLE_COLORS[role] || "bg-slate-600")}>
                {user.split(" ").map(w => w[0]).join("").slice(0, 2).toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-semibold text-white truncate">{user}</p>
                <p className="text-[10px] text-slate-400 capitalize">Global {role}</p>
              </div>
              <button onClick={handleLogout} title="Sign out" className="text-slate-400 hover:text-red-400 transition-colors">
                <LogOut className="h-3.5 w-3.5" />
              </button>
            </div>
          )}
          <button
            onClick={() => setCollapsed(c => !c)}
            className="flex items-center gap-2 w-full px-3 py-2 rounded-lg text-slate-400 hover:bg-slate-700 hover:text-white transition-colors text-[13px]"
          >
            {collapsed ? <ChevronRight className="h-4 w-4" /> : <><ChevronLeft className="h-4 w-4" /><span>Collapse</span></>}
          </button>
        </div>
      </aside>

      {/* ── Main area ───────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col overflow-hidden">

        {/* Top bar */}
        <header className="h-14 bg-white border-b border-slate-200 flex items-center gap-4 px-6 flex-shrink-0 shadow-sm">
          <div className="flex-1 flex items-center gap-3">
            <div className="relative">
              <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                placeholder="Search invoices, cases, carriers, contracts..."
                className="pl-9 pr-12 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-600 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/30 w-80"
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-slate-400 font-mono bg-slate-100 px-1 rounded">⌘K</span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Date range */}
            <button className="flex items-center gap-2 px-3 py-2 rounded-lg border border-slate-200 text-sm text-slate-600 hover:bg-slate-50">
              <span>Jul 01 – Jul 24, 2025</span>
              <Calendar className="h-4 w-4 text-slate-400" />
            </button>

            {/* Actions */}
            <button className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-slate-200 text-sm text-slate-600 hover:bg-slate-50">
              Actions <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
            </button>

            {/* Export */}
            <button className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-slate-200 text-sm text-slate-600 hover:bg-slate-50">
              <Download className="h-4 w-4" /> Export
            </button>

            {/* Notifications */}
            <button className="relative p-2 rounded-lg hover:bg-slate-50">
              <Bell className="h-4.5 w-4.5 text-slate-500" />
              <span className="absolute top-1 right-1 h-4 w-4 bg-red-500 rounded-full text-[9px] text-white flex items-center justify-center font-bold">12</span>
            </button>

            {/* User avatar */}
            <div className="flex items-center gap-2">
              <div className={cn("h-8 w-8 rounded-full flex items-center justify-center text-white text-xs font-bold", ROLE_COLORS[role] || "bg-slate-600")}>
                {user.split(" ").map(w => w[0]).join("").slice(0, 2).toUpperCase()}
              </div>
              <div className="hidden md:block">
                <p className="text-sm font-semibold text-slate-700 leading-tight">{user}</p>
                <p className="text-[10px] text-slate-400 capitalize">Global {role}</p>
              </div>
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto">
          <div className="px-6 py-5 max-w-[1600px] mx-auto">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
