/// <reference types="vite/client" />
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { zoikoApi } from "@/api/zoiko";
import { cn } from "@/utils/cn";
import {
  LayoutDashboard, FolderOpen, PlusCircle, ClipboardList,
  CheckSquare, Zap, ShieldCheck, Database, MessageSquare,
  LogOut, ChevronDown, ChevronRight, Bell, BarChart2, Settings,
} from "lucide-react";
import { useState, useEffect } from "react";
import { useLocation } from "react-router-dom";

const ROLE_COLORS: Record<string, string> = {
  analyst: "bg-zoiko-blue",
  manager: "bg-zoiko-purple",
  admin:   "bg-zoiko-navy",
};

function NavItem({ to, label, icon: Icon, badge, end }: {
  to: string; label: string; icon: React.ElementType; badge?: number; end?: boolean;
}) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) => cn(
        "flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-colors",
        isActive
          ? "bg-zoiko-navy text-white shadow-sm"
          : "text-foreground/70 hover:bg-secondary hover:text-foreground"
      )}
    >
      <div className="flex items-center gap-2.5">
        <Icon className="h-4 w-4 flex-shrink-0" />
        <span className="truncate font-medium">{label}</span>
      </div>
      {badge != null && badge > 0 && (
        <span className="ml-2 flex h-5 min-w-[20px] items-center justify-center rounded-full bg-destructive text-[10px] font-bold text-white px-1 flex-shrink-0">
          {badge > 9 ? "9+" : badge}
        </span>
      )}
    </NavLink>
  );
}

export default function AppLayout() {
  const nav2     = useNavigate();
  const location = useLocation();
  const user     = localStorage.getItem("zoiko_user")   || "User";
  const role     = localStorage.getItem("zoiko_role")   || "analyst";
  const isLive   = import.meta.env.VITE_USE_MOCK === "false";
  const [systemOpen,   setSystemOpen]   = useState(false);
  const [alertBadge,   setAlertBadge]   = useState<number>(() => {
    const seen = localStorage.getItem("zoiko_alerts_seen_date");
    return seen === new Date().toDateString() ? 0 : 3;
  });

  useEffect(() => {
    if (location.pathname === "/alerts") {
      localStorage.setItem("zoiko_alerts_seen_date", new Date().toDateString());
      setAlertBadge(0);
    }
  }, [location.pathname]);

  const { data: cases } = useQuery({ queryKey: ["cases"], queryFn: () => zoikoApi.listCases() });
  const reviewCount   = cases?.filter(c => ["NEW", "EVIDENCE_PENDING", "FINDING_GENERATED"].includes(c.state)).length ?? 0;
  const approvalCount = cases?.filter(c => c.state === "APPROVAL_PENDING").length ?? 0;

  function handleLogout() {
    localStorage.removeItem("zoiko_role");
    localStorage.removeItem("zoiko_user");
    localStorage.removeItem("zoiko_sub");
    localStorage.removeItem("zoiko_tenant");
    nav2("/login");
  }

  return (
    <div className="flex h-screen bg-gray-50">
      <aside className="w-60 bg-white border-r flex-shrink-0 flex flex-col shadow-sm">

        {/* Logo */}
        <div className="px-5 py-4 border-b flex-shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="h-9 w-9 rounded-xl bg-zoiko-navy flex items-center justify-center text-white font-bold text-base shadow">Z</div>
            <div>
              <p className="font-bold text-zoiko-navy text-sm leading-tight">Zoiko AI</p>
              <p className="text-[10px] text-muted-foreground tracking-wide">Freight Audit Platform</p>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="px-3 py-4 flex-1 overflow-y-auto space-y-5">

          {/* Overview */}
          <div>
            <p className="px-3 mb-1.5 text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">Overview</p>
            <div className="space-y-0.5">
              <NavItem to="/"      label="Live Monitor"  icon={LayoutDashboard} end />
              <NavItem to="/cases" label="All Cases"     icon={FolderOpen} />
              {(role === "analyst" || role === "admin") && (
                <NavItem to="/cases/new" label="New Case" icon={PlusCircle} />
              )}
            </div>
          </div>

          {/* Workflow */}
          <div>
            <p className="px-3 mb-1.5 text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">Workflow</p>
            <div className="space-y-0.5">
              {(role === "analyst" || role === "admin") && (
                <NavItem to="/analyst" label="Analyst Review"   icon={ClipboardList} badge={reviewCount} />
              )}
              {(role === "manager" || role === "admin") && (
                <NavItem to="/manager" label="Manager Approval" icon={CheckSquare} badge={approvalCount} />
              )}
              {(role === "manager" || role === "admin") && (
                <NavItem to="/execute" label="Recovery Tracker" icon={Zap} />
              )}
            </div>
          </div>

          {/* Insights */}
          <div>
            <p className="px-3 mb-1.5 text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">Insights</p>
            <div className="space-y-0.5">
              <NavItem to="/alerts"    label="Alerts"           icon={Bell} badge={alertBadge} />
              <NavItem to="/analytics" label="Analytics"        icon={BarChart2} />
            </div>
          </div>

          {/* System — admin only */}
          {role === "admin" && (
            <div>
              <button
                onClick={() => setSystemOpen(s => !s)}
                className="flex items-center justify-between w-full px-3 mb-1.5 text-[10px] uppercase tracking-wider text-muted-foreground font-semibold hover:text-foreground transition-colors"
              >
                System
                {systemOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
              </button>
              {systemOpen && (
                <div className="space-y-0.5">
                  <NavItem to="/crypto"   label="Audit Reports"  icon={ShieldCheck} />
                  <NavItem to="/settings" label="Settings"       icon={Settings} />
                  <NavItem to="/database" label="Database"       icon={Database} />
                  <NavItem to="/kafka"    label="Event Log"      icon={MessageSquare} />
                </div>
              )}
            </div>
          )}
        </nav>

        {/* Mode pill */}
        <div className={cn(
          "mx-3 mb-2 rounded-lg px-3 py-1.5 text-[10px] font-semibold flex items-center gap-1.5",
          isLive ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"
        )}>
          <span className={cn("h-1.5 w-1.5 rounded-full flex-shrink-0 animate-pulse", isLive ? "bg-emerald-500" : "bg-amber-500")} />
          {isLive ? "Connected · Live" : "Mock mode · Demo data"}
        </div>

        {/* User + logout */}
        <div className="px-4 py-3 border-t flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className={cn("h-8 w-8 rounded-full flex items-center justify-center text-white text-xs font-bold flex-shrink-0", ROLE_COLORS[role] || "bg-zoiko-navy")}>
              {user.split(" ").map(w => w[0]).join("").slice(0, 2).toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold truncate">{user}</p>
              <p className="text-[10px] text-muted-foreground capitalize">{role} · amazon-india</p>
            </div>
            <button onClick={handleLogout} title="Sign out" className="text-muted-foreground hover:text-destructive transition-colors flex-shrink-0">
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto">
        <div className="px-8 py-6 max-w-7xl mx-auto">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
