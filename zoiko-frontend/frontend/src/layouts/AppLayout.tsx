import { NavLink, Outlet, useNavigate, useLocation } from "react-router-dom";
import { useAppDispatch, useAppSelector } from "@/store";
import { logout as logoutAction } from "@/store/authSlice";
import { queryClient } from "@/lib/queryClient";
import axios from "axios";
import { cn } from "@/utils/cn";
import {
  LayoutDashboard, FileText, FolderOpen, FileWarning,
  FileClock, Truck, ShieldCheck, BookOpen,
  Key, Archive, ClipboardList,
  BarChart3, TrendingUp,
  Users, Settings, Building2, Bell, Search,
  ChevronLeft, ChevronRight, LogOut, Calendar, ChevronDown,
  Zap, CheckSquare, FlaskConical, Plug,
  Activity, Lock, Clock, ShieldOff, RotateCcw, HardDrive, Trash2,
  Wallet, Scale, AlertTriangle, Plus, X, Sun, Moon,
} from "lucide-react";
import { useState, useRef, useEffect } from "react";

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
      { label: "Dashboard",           icon: LayoutDashboard, to: "/"                  },
      { label: "Invoices & Cases",    icon: FolderOpen,      to: "/cases"             },
      { label: "Submit Invoice",      icon: FileText,        to: "/cases/new"         },
      { label: "Carrier Claims",      icon: FileWarning,     to: "/claims"            },
      { label: "Submit Claim",        icon: FileWarning,     to: "/claims/new"        },
      { label: "Shipment Exceptions", icon: AlertTriangle,   to: "/exceptions"        },
      { label: "Report Exception",    icon: Plus,            to: "/exceptions/new"    },
      { label: "Audit Conditions",    icon: CheckSquare,     to: "/audit-conditions"  },
      { label: "Contracts & Rates",   icon: FileClock,       to: "/rate-control"      },
      { label: "Carriers",            icon: Truck,           to: "/carriers"          },
      { label: "Connectors",          icon: Plug,            to: "/connectors"        },
    ],
  },
  {
    group: "GOVERNANCE",
    items: [
      { label: "Analyst Review",    icon: BookOpen,     to: "/analyst",        roles: ["analyst","admin"]       },
      { label: "Manager Approval",  icon: ShieldCheck,  to: "/manager",        roles: ["manager","admin"]       },
      { label: "Execute Recovery",  icon: Zap,          to: "/execute",        roles: ["manager","admin"]       },
      { label: "Gov. Tokens",       icon: Key,          to: "/execute",        roles: ["manager","admin"]       },
      { label: "Recovery Pipeline", icon: Wallet,       to: "/recovery"                                        },
      { label: "Reconciliation",    icon: Scale,        to: "/reconciliation", roles: ["manager","admin"]       },
      { label: "Audit & ACR",       icon: Archive,      to: "/crypto"                                          },
      { label: "ACR Verifier",      icon: ShieldCheck,  to: "/verifier"                                        },
      { label: "Audit Trail",       icon: ClipboardList,to: "/alerts"                                          },
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
    group: "DATA GOVERNANCE",
    roles: ["admin"],
    items: [
      { label: "Gov. Dashboard", icon: Activity,  to: "/governance/data"         },
      { label: "Legal Holds",    icon: Lock,      to: "/governance/holds"        },
      { label: "Retention",      icon: Clock,     to: "/governance/retention"    },
      { label: "Crypto-Shred",   icon: ShieldOff, to: "/governance/crypto-shred" },
      { label: "Restore Jobs",   icon: RotateCcw, to: "/governance/restore"      },
      { label: "Archive Jobs",   icon: HardDrive, to: "/governance/archive"      },
      { label: "Purge Jobs",     icon: Trash2,    to: "/governance/purge"        },
    ],
  },
  {
    group: "ADMIN",
    roles: ["admin"],
    items: [
      { label: "Tenants",         icon: Building2,    to: "/tenants"                          },
      { label: "Signup Requests", icon: Users,        to: "/workspace-requests", badge: "NEW" },
      { label: "Users & Roles",   icon: Users,        to: "/users"                            },
      { label: "DB Stats",        icon: Building2,    to: "/database"                         },
      { label: "Settings",        icon: Settings,     to: "/settings"                         },
      { label: "Stub Viewer",     icon: FlaskConical, to: "/stubs",              badge: "DEV" },
    ],
  },
];

function NavItem({ to, label, icon: Icon, collapsed, badge }: {
  to: string; label: string; icon: React.ElementType; collapsed: boolean; badge?: string;
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
          : "text-slate-300/80 font-medium hover:bg-white/5 hover:text-slate-100"
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

const MONTH_NAMES = [
  "January","February","March","April","May","June",
  "July","August","September","October","November","December",
];
const DAY_NAMES = ["Su","Mo","Tu","We","Th","Fr","Sa"];

type NotifItem = {
  id: number;
  icon: React.ElementType;
  color: string;
  bg: string;
  darkBg: string;
  title: string;
  body: string;
  time: string;
};

const NOTIF_ITEMS: NotifItem[] = [
  { id: 1, icon: AlertTriangle, color: "text-orange-500", bg: "bg-orange-50",  darkBg: "dark:bg-orange-500/10", title: "New overcharge detected",   body: "BlueDart case · ₹4,500 overcharge vs contract",  time: "4 min ago"  },
  { id: 2, icon: Clock,         color: "text-amber-500",  bg: "bg-amber-50",   darkBg: "dark:bg-amber-500/10",  title: "Approval required",         body: "Case SC-001-2841 awaiting manager decision",       time: "18 min ago" },
  { id: 3, icon: CheckSquare,   color: "text-emerald-500",bg: "bg-emerald-50", darkBg: "dark:bg-emerald-500/10",title: "Recovery completed",        body: "₹3,200 recovered from DHL Logistics",             time: "1 hr ago"   },
  { id: 4, icon: Key,           color: "text-blue-500",   bg: "bg-blue-50",    darkBg: "dark:bg-blue-500/10",   title: "Governance token expiring", body: "Token for case SC-001-2838 expires in 5 min",     time: "2 hr ago"   },
  { id: 5, icon: Archive,       color: "text-slate-400",  bg: "bg-slate-100",  darkBg: "dark:bg-slate-700",     title: "Audit record locked",       body: "ACR issued for SC-001-2835 — WORM locked",        time: "3 hr ago"   },
];

export default function AppLayout() {
  const nav      = useNavigate();
  const location = useLocation();
  const dispatch = useAppDispatch();
  const user = useAppSelector(s => s.auth.user) || "User";
  const role = useAppSelector(s => s.auth.role) || "analyst";

  const [collapsed,    setCollapsed]    = useState(false);
  const [darkMode,     setDarkMode]     = useState(() => {
    const saved = localStorage.getItem("zoiko-theme");
    return saved === "dark" || (!saved && window.matchMedia("(prefers-color-scheme: dark)").matches);
  });
  const [searchQuery,  setSearchQuery]  = useState("");
  const [profileOpen,  setProfileOpen]  = useState(false);
  const [notifOpen,    setNotifOpen]    = useState(false);
  const [actionsOpen,  setActionsOpen]  = useState(false);
  const [calendarOpen, setCalendarOpen] = useState(false);
  const [calViewDate,  setCalViewDate]  = useState(() => new Date());
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [notifCount,   setNotifCount]   = useState(3);

  const profileRef = useRef<HTMLDivElement>(null);
  const notifRef   = useRef<HTMLDivElement>(null);
  const actionsRef = useRef<HTMLDivElement>(null);
  const calRef     = useRef<HTMLDivElement>(null);
  const searchRef  = useRef<HTMLInputElement>(null);

  // Apply / remove dark class and persist preference
  useEffect(() => {
    if (darkMode) {
      document.documentElement.classList.add("dark");
      localStorage.setItem("zoiko-theme", "dark");
    } else {
      document.documentElement.classList.remove("dark");
      localStorage.setItem("zoiko-theme", "light");
    }
  }, [darkMode]);

  // Close any open dropdown when clicking outside
  useEffect(() => {
    function handleDown(e: MouseEvent) {
      if (profileRef.current && !profileRef.current.contains(e.target as Node)) setProfileOpen(false);
      if (notifRef.current   && !notifRef.current.contains(e.target as Node))   setNotifOpen(false);
      if (actionsRef.current && !actionsRef.current.contains(e.target as Node)) setActionsOpen(false);
      if (calRef.current     && !calRef.current.contains(e.target as Node))     setCalendarOpen(false);
    }
    document.addEventListener("mousedown", handleDown);
    return () => document.removeEventListener("mousedown", handleDown);
  }, []);

  // ⌘K / Ctrl+K focuses search; Escape closes everything
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        searchRef.current?.focus();
      }
      if (e.key === "Escape") {
        setProfileOpen(false);
        setNotifOpen(false);
        setActionsOpen(false);
        setCalendarOpen(false);
        searchRef.current?.blur();
      }
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, []);

  function closeAllDropdowns() {
    setProfileOpen(false);
    setNotifOpen(false);
    setActionsOpen(false);
    setCalendarOpen(false);
  }

  function handleLogout() {
    axios.post("/api/v1/auth/signout", {}, { withCredentials: true }).catch(() => {});
    dispatch(logoutAction());
    queryClient.clear();
    nav("/login");
  }

  function handleSearchSubmit(e: React.FormEvent) {
    e.preventDefault();
    const q = searchQuery.trim();
    if (!q) return;
    if (location.pathname.startsWith("/claims")) {
      nav(`/claims?q=${encodeURIComponent(q)}`);
    } else {
      nav(`/cases?q=${encodeURIComponent(q)}`);
    }
    setSearchQuery("");
    searchRef.current?.blur();
  }

  function handleDateSelect(year: number, month: number, day: number) {
    const dateStr = `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    setSelectedDate(dateStr);
    setCalendarOpen(false);
    nav(`/cases?date=${dateStr}`);
  }

  const calYear        = calViewDate.getFullYear();
  const calMonth       = calViewDate.getMonth();
  const firstDayOffset = new Date(calYear, calMonth, 1).getDay();
  const daysInMonth    = new Date(calYear, calMonth + 1, 0).getDate();
  const todayObj       = new Date();

  const initials = (user || "U")
    .split(" ")
    .map((w: string) => w[0] || "")
    .join("")
    .slice(0, 2)
    .toUpperCase() || "U";

  const allItems   = NAV.flatMap(g => g.items);
  const activeItem = allItems.find(item =>
    item.to === "/" ? location.pathname === "/" : location.pathname.startsWith(item.to)
  );
  const pageTitle = activeItem?.label ?? "Dashboard";

  const calButtonLabel = selectedDate
    ? new Date(selectedDate + "T00:00:00").toLocaleDateString("en-IN", {
        day: "numeric", month: "short", year: "numeric",
      })
    : `${MONTH_NAMES[calMonth].slice(0, 3)} ${calYear}`;

  // Reusable dark-mode dropdown panel classes
  const dropdownPanel = "absolute right-0 top-full mt-2 z-50 overflow-hidden rounded-xl shadow-xl border bg-white dark:bg-slate-900 border-slate-100 dark:border-slate-700";

  return (
    <div className="flex h-screen bg-slate-100 dark:bg-slate-950 overflow-hidden">

      {/* ── Sidebar ─────────────────────────────────────────────────────── */}
      <aside className={cn(
        "flex flex-col border-r border-slate-700/40 transition-all duration-200 flex-shrink-0 relative",
        "bg-[#0d1424] dark:bg-[#080d1a]",
        collapsed ? "w-[60px]" : "w-[220px]"
      )}>
        <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-blue-600 via-blue-500 to-cyan-500" />

        {/* Logo */}
        <div className={cn(
          "flex items-center justify-center border-b border-slate-700/40 flex-shrink-0",
          collapsed ? "px-2 py-4" : "px-3 py-4"
        )}>
          {collapsed ? (
            <img src="/logo-icon.svg" alt="Z" className="h-8 w-8 object-contain"
              onError={e => { const t = e.currentTarget; t.style.display = "none"; const fb = t.nextElementSibling as HTMLElement | null; if (fb) fb.style.display = "flex"; }}
            />
          ) : (
            <img src="/logo-dark.jpg" alt="ZoikoAI" className="h-10 w-auto object-contain"
              onError={e => { const t = e.currentTarget; t.style.display = "none"; const fb = t.nextElementSibling as HTMLElement | null; if (fb) fb.style.display = "flex"; }}
            />
          )}
          <div className="hidden items-center gap-2">
            <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-blue-500 to-blue-700 flex items-center justify-center text-white font-bold text-sm flex-shrink-0">Z</div>
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
                  <p className="px-3 mb-1.5 text-[9px] font-bold tracking-[0.12em] text-slate-500/70 uppercase select-none">{group}</p>
                )}
                {collapsed && <div className="h-px bg-slate-700/40 mx-2 mb-2 mt-1" />}
                <div className="space-y-0.5">
                  {visibleItems.map(item => (
                    <NavItem key={item.label + item.to} to={item.to} label={item.label} icon={item.icon} collapsed={collapsed} badge={item.badge} />
                  ))}
                </div>
              </div>
            );
          })}
        </nav>

        {/* Footer: collapse toggle */}
        <div className="border-t border-slate-700/40 px-2 py-3 flex-shrink-0">
          <button
            onClick={() => setCollapsed(c => !c)}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className="flex items-center gap-2 w-full px-3 py-2 rounded-lg text-slate-400/70 hover:bg-white/5 hover:text-slate-300 transition-colors text-[12px]"
          >
            {collapsed
              ? <ChevronRight className="h-4 w-4 mx-auto" />
              : <><ChevronLeft className="h-4 w-4" /><span>Collapse</span></>
            }
          </button>
        </div>
      </aside>

      {/* ── Main ─────────────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col overflow-hidden">

        {/* ── Top bar ──────────────────────────────────────────────────── */}
        <header className="h-[56px] flex items-center gap-4 px-5 flex-shrink-0 relative z-40
          bg-white dark:bg-slate-900
          border-b border-slate-200 dark:border-slate-700
          shadow-sm dark:shadow-slate-900/50">

          {/* Page title */}
          <div className="font-semibold text-sm hidden sm:block shrink-0 text-slate-700 dark:text-slate-200">
            {pageTitle}
          </div>

          {/* Global search */}
          <div className="flex-1 flex items-center">
            <form onSubmit={handleSearchSubmit} className="relative">
              <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 dark:text-slate-500 pointer-events-none" />
              <input
                ref={searchRef}
                type="text"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                placeholder="Search invoices, cases, carriers…"
                className="pl-9 pr-10 py-1.5 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/30 w-64 transition-all focus:w-80
                  bg-slate-50 dark:bg-slate-800
                  border border-slate-200 dark:border-slate-600
                  text-slate-600 dark:text-slate-200
                  placeholder:text-slate-400 dark:placeholder:text-slate-500"
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] font-mono px-1 rounded select-none
                text-slate-400 dark:text-slate-500
                bg-slate-100 dark:bg-slate-700">
                ⌘K
              </span>
            </form>
          </div>

          <div className="flex items-center gap-2">

            {/* ── Calendar picker ──────────────────────────────────────── */}
            <div ref={calRef} className="relative hidden md:block">
              <button
                onClick={() => { const o = !calendarOpen; closeAllDropdowns(); setCalendarOpen(o); }}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs transition-colors",
                  calendarOpen
                    ? "border-blue-400 bg-blue-50 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400"
                    : "border-slate-200 dark:border-slate-600 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800"
                )}
              >
                <Calendar className="h-3.5 w-3.5 text-slate-400 dark:text-slate-500" />
                <span>{calButtonLabel}</span>
              </button>

              {calendarOpen && (
                <div className={cn(dropdownPanel, "w-72")}>
                  <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/60">
                    <button
                      onClick={() => setCalViewDate(d => new Date(d.getFullYear(), d.getMonth() - 1, 1))}
                      className="p-1.5 rounded-lg text-slate-500 dark:text-slate-400 hover:bg-white dark:hover:bg-slate-700 hover:text-slate-700 dark:hover:text-slate-200 transition-colors"
                    >
                      <ChevronLeft className="h-4 w-4" />
                    </button>
                    <span className="text-sm font-semibold text-slate-700 dark:text-slate-200">
                      {MONTH_NAMES[calMonth]} {calYear}
                    </span>
                    <button
                      onClick={() => setCalViewDate(d => new Date(d.getFullYear(), d.getMonth() + 1, 1))}
                      className="p-1.5 rounded-lg text-slate-500 dark:text-slate-400 hover:bg-white dark:hover:bg-slate-700 hover:text-slate-700 dark:hover:text-slate-200 transition-colors"
                    >
                      <ChevronRight className="h-4 w-4" />
                    </button>
                  </div>

                  <div className="grid grid-cols-7 px-3 pt-2 pb-1">
                    {DAY_NAMES.map(d => (
                      <div key={d} className="text-center text-[10px] font-bold text-slate-400 dark:text-slate-500 py-1">{d}</div>
                    ))}
                  </div>

                  <div className="grid grid-cols-7 px-3 pb-2 gap-y-0.5">
                    {Array.from({ length: firstDayOffset }, (_, i) => <div key={`e${i}`} />)}
                    {Array.from({ length: daysInMonth }, (_, i) => {
                      const day = i + 1;
                      const isToday = todayObj.getFullYear() === calYear && todayObj.getMonth() === calMonth && todayObj.getDate() === day;
                      const dateStr = `${calYear}-${String(calMonth + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
                      const isSel   = selectedDate === dateStr;
                      return (
                        <button
                          key={day}
                          onClick={() => handleDateSelect(calYear, calMonth, day)}
                          className={cn(
                            "text-center text-xs py-1.5 rounded-lg transition-colors font-medium",
                            isSel    ? "bg-blue-600 text-white shadow-sm shadow-blue-400/40" :
                            isToday  ? "bg-blue-100 dark:bg-blue-500/20 text-blue-700 dark:text-blue-400 font-bold" :
                                       "text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700"
                          )}
                        >
                          {day}
                        </button>
                      );
                    })}
                  </div>

                  <div className="px-3 pb-3 flex items-center gap-2">
                    <button
                      onClick={() => { const now = new Date(); setCalViewDate(now); handleDateSelect(now.getFullYear(), now.getMonth(), now.getDate()); }}
                      className="flex-1 text-xs text-blue-600 dark:text-blue-400 hover:text-blue-700 py-1.5 border border-blue-200 dark:border-blue-500/40 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-500/10 transition-colors font-medium"
                    >
                      Today
                    </button>
                    {selectedDate && (
                      <button
                        onClick={() => { setSelectedDate(null); nav("/cases"); setCalendarOpen(false); }}
                        className="flex-1 text-xs text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 py-1.5 border border-slate-200 dark:border-slate-600 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
                      >
                        Clear filter
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* ── Actions dropdown ──────────────────────────────────────── */}
            <div ref={actionsRef} className="relative hidden md:block">
              <button
                onClick={() => { const o = !actionsOpen; closeAllDropdowns(); setActionsOpen(o); }}
                className={cn(
                  "flex items-center gap-1 px-3 py-1.5 rounded-lg border text-xs transition-colors",
                  actionsOpen
                    ? "border-blue-400 bg-blue-50 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400"
                    : "border-slate-200 dark:border-slate-600 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800"
                )}
              >
                Actions
                <ChevronDown className={cn("h-3 w-3 text-slate-400 dark:text-slate-500 transition-transform duration-150", actionsOpen && "rotate-180")} />
              </button>

              {actionsOpen && (
                <div className={cn(dropdownPanel, "w-52")}>
                  <div className="px-3 pt-2.5 pb-1 text-[10px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider">
                    Quick Actions
                  </div>
                  {[
                    { label: "Submit New Invoice", icon: FileText,      to: "/cases/new"      },
                    { label: "Submit New Claim",   icon: FileWarning,   to: "/claims/new"     },
                    { label: "Report Exception",   icon: AlertTriangle, to: "/exceptions/new" },
                  ].map(({ label, icon: Icon, to }) => (
                    <button
                      key={to}
                      onClick={() => { nav(to); setActionsOpen(false); }}
                      className="flex items-center gap-2.5 w-full px-3 py-2.5 text-sm text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
                    >
                      <Icon className="h-4 w-4 text-slate-400 dark:text-slate-500" />
                      {label}
                    </button>
                  ))}
                  <div className="border-t border-slate-100 dark:border-slate-700 mt-1 pt-1 pb-1">
                    {[
                      { label: "Execute Recovery", icon: Zap,      to: "/execute"    },
                      { label: "View Analytics",   icon: BarChart3, to: "/analytics" },
                    ].map(({ label, icon: Icon, to }) => (
                      <button
                        key={to}
                        onClick={() => { nav(to); setActionsOpen(false); }}
                        className="flex items-center gap-2.5 w-full px-3 py-2.5 text-sm text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
                      >
                        <Icon className="h-4 w-4 text-slate-400 dark:text-slate-500" />
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* ── Theme toggle ─────────────────────────────────────────── */}
            <button
              onClick={() => setDarkMode(d => !d)}
              title={darkMode ? "Switch to light mode" : "Switch to dark mode"}
              className="hidden md:flex items-center justify-center p-2 rounded-lg border transition-colors
                border-slate-200 dark:border-slate-600
                text-slate-500 dark:text-slate-400
                hover:bg-slate-50 dark:hover:bg-slate-800
                hover:text-slate-700 dark:hover:text-slate-200"
            >
              {darkMode
                ? <Sun  className="h-4 w-4 text-amber-400" />
                : <Moon className="h-4 w-4" />
              }
            </button>

            {/* ── Notifications ────────────────────────────────────────── */}
            <div ref={notifRef} className="relative">
              <button
                onClick={() => { const o = !notifOpen; closeAllDropdowns(); setNotifOpen(o); }}
                className={cn(
                  "relative p-2 rounded-lg transition-colors",
                  notifOpen
                    ? "bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200"
                    : "text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800"
                )}
              >
                <Bell className="h-4 w-4" />
                {notifCount > 0 && (
                  <span className="absolute top-1 right-1 h-3.5 w-3.5 bg-red-500 rounded-full text-[8px] text-white flex items-center justify-center font-bold leading-none">
                    {notifCount}
                  </span>
                )}
              </button>

              {notifOpen && (
                <div className={cn(dropdownPanel, "w-80")}>
                  <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/60">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-slate-700 dark:text-slate-200">Notifications</span>
                      {notifCount > 0 && (
                        <span className="text-[10px] font-bold bg-red-100 dark:bg-red-500/15 text-red-600 dark:text-red-400 px-1.5 py-0.5 rounded-full">
                          {notifCount} new
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      {notifCount > 0 && (
                        <button onClick={() => setNotifCount(0)} className="text-[11px] text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 font-medium transition-colors">
                          Mark all read
                        </button>
                      )}
                      <button onClick={() => setNotifOpen(false)} className="p-1 rounded-lg hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 transition-colors">
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>

                  <div className="max-h-80 overflow-y-auto divide-y divide-slate-50 dark:divide-slate-800">
                    {NOTIF_ITEMS.map((n, idx) => {
                      const isUnread = idx < notifCount;
                      return (
                        <button
                          key={n.id}
                          onClick={() => { if (isUnread) setNotifCount(c => Math.max(0, c - 1)); setNotifOpen(false); nav("/alerts"); }}
                          className="flex items-start gap-3 w-full px-4 py-3 hover:bg-slate-50 dark:hover:bg-slate-800/70 transition-colors text-left"
                        >
                          <div className={cn("h-8 w-8 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5", n.bg, n.darkBg)}>
                            <n.icon className={cn("h-4 w-4", n.color)} />
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className={cn("text-xs font-semibold leading-snug", isUnread ? "text-slate-800 dark:text-slate-100" : "text-slate-500 dark:text-slate-500")}>
                              {n.title}
                            </p>
                            <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5 truncate">{n.body}</p>
                            <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-1">{n.time}</p>
                          </div>
                          {isUnread && <div className="h-2 w-2 bg-blue-500 rounded-full flex-shrink-0 mt-2" />}
                        </button>
                      );
                    })}
                  </div>

                  <div className="px-4 py-2.5 border-t border-slate-100 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/60">
                    <button onClick={() => { nav("/alerts"); setNotifOpen(false); }} className="text-xs text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 font-medium transition-colors">
                      View all activity →
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* ── Profile dropdown ─────────────────────────────────────── */}
            <div ref={profileRef} className="relative">
              <button
                onClick={() => { const o = !profileOpen; closeAllDropdowns(); setProfileOpen(o); }}
                className={cn(
                  "flex items-center gap-2 pl-2 pr-1.5 py-1 rounded-lg border transition-colors",
                  profileOpen
                    ? "border-blue-200 dark:border-blue-500/40 bg-blue-50 dark:bg-blue-500/10"
                    : "border-transparent hover:border-slate-200 dark:hover:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-800"
                )}
              >
                <div className={cn(
                  "h-7 w-7 rounded-full bg-gradient-to-br flex items-center justify-center text-white text-[11px] font-bold flex-shrink-0",
                  ROLE_COLORS[role] || "from-slate-500 to-slate-700"
                )}>
                  {initials}
                </div>
                <div className="hidden lg:block text-left">
                  <p className="text-xs font-semibold leading-tight text-slate-700 dark:text-slate-200">{user}</p>
                  <span style={{
                    fontSize: 9, fontWeight: 700, padding: "1px 6px", borderRadius: 99,
                    background: role === "admin" ? "#1e3a8a" : role === "manager" ? "#4c1d95" : "#064e3b",
                    color: "#fff", textTransform: "uppercase" as const, letterSpacing: "0.06em",
                  }}>
                    {role}
                  </span>
                </div>
                <ChevronDown className={cn("h-3.5 w-3.5 text-slate-400 dark:text-slate-500 hidden lg:block transition-transform duration-150", profileOpen && "rotate-180")} />
              </button>

              {profileOpen && (
                <div className={cn(dropdownPanel, "w-56")}>
                  <div className="px-4 py-3.5 border-b border-slate-100 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/60">
                    <div className="flex items-center gap-3">
                      <div className={cn(
                        "h-10 w-10 rounded-full bg-gradient-to-br flex items-center justify-center text-white text-sm font-bold flex-shrink-0 shadow-sm",
                        ROLE_COLORS[role] || "from-slate-500 to-slate-700"
                      )}>
                        {initials}
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-slate-800 dark:text-slate-100 truncate">{user}</p>
                        <p className="text-[11px] text-slate-500 dark:text-slate-400 capitalize mt-0.5">{role}</p>
                      </div>
                    </div>
                  </div>

                  <div className="py-1">
                    <button onClick={() => { nav("/settings"); setProfileOpen(false); }}
                      className="flex items-center gap-2.5 w-full px-4 py-2.5 text-sm text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors">
                      <Settings className="h-4 w-4 text-slate-400 dark:text-slate-500" />
                      Settings
                    </button>
                    <button onClick={() => { nav("/users"); setProfileOpen(false); }}
                      className="flex items-center gap-2.5 w-full px-4 py-2.5 text-sm text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors">
                      <Users className="h-4 w-4 text-slate-400 dark:text-slate-500" />
                      Account
                    </button>
                  </div>

                  <div className="border-t border-slate-100 dark:border-slate-700 py-1">
                    <button onClick={handleLogout}
                      className="flex items-center gap-2.5 w-full px-4 py-2.5 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors">
                      <LogOut className="h-4 w-4" />
                      Sign out
                    </button>
                  </div>
                </div>
              )}
            </div>

          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto bg-slate-50 dark:bg-slate-950">
          <div className="px-6 py-5 max-w-[1600px] mx-auto">
            <Outlet />
          </div>
        </main>

      </div>
    </div>
  );
}
