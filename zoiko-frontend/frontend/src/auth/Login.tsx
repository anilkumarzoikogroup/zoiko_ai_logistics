import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ShieldCheck, CheckCircle2, ArrowRight, Lock, Zap,
  GitBranch, BarChart3, Award, ChevronRight,
} from "lucide-react";
import { cn } from "@/utils/cn";

const TENANT_ID = "11111111-1111-1111-1111-111111111111";

const ROLES = [
  {
    id: "analyst",
    name: "Ravi Kumar",
    title: "Freight Analyst",
    company: "Amazon India",
    avatar: "RK",
    color: "from-blue-500 to-blue-700",
    ring: "ring-blue-400",
    badge: "bg-blue-100 text-blue-700",
    description: "Reviews flagged invoices, runs AI analysis, proposes recovery actions.",
    capabilities: ["View all cases", "Propose recovery", "Add evidence", "View AI findings"],
    jwt_sub: "ravi@amazon.com",
    jwt: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJyYXZpQGFtYXpvbi5jb20iLCJpc3MiOiJodHRwczovL2F1dGguem9pa290ZWNoLmNvbSIsImF1ZCI6InpvaWtvLWRldiIsImlhdCI6MTc3OTcwMzIxNSwiZXhwIjoxNzgyMjk1MjE1LCJ0ZW5hbnRfaWQiOiIxMTExMTExMS0xMTExLTExMTEtMTExMS0xMTExMTExMTExMTEiLCJyb2xlcyI6WyJhbmFseXN0Il0sInpvaWtvX2VudiI6ImRldiJ9.9peP5gzIdeZI2dYnzFVn0kfaUSGk8NW3U_PJxqaeB7A",
  },
  {
    id: "manager",
    name: "Ramu Sharma",
    title: "Finance Manager",
    company: "Amazon India",
    avatar: "RS",
    color: "from-violet-500 to-purple-700",
    ring: "ring-violet-400",
    badge: "bg-violet-100 text-violet-700",
    description: "Final approver for recovery decisions. Enforced separation of duties (SoD).",
    capabilities: ["Approve / Reject proposals", "View audit trail", "View tokens", "Execute recovery"],
    jwt_sub: "ramu@amazon.com",
    jwt: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJyYW11QGFtYXpvbi5jb20iLCJpc3MiOiJodHRwczovL2F1dGguem9pa290ZWNoLmNvbSIsImF1ZCI6InpvaWtvLWRldiIsImlhdCI6MTc3OTcwMzIxNSwiZXhwIjoxNzgyMjk1MjE1LCJ0ZW5hbnRfaWQiOiIxMTExMTExMS0xMTExLTExMTEtMTExMS0xMTExMTExMTExMTEiLCJyb2xlcyI6WyJtYW5hZ2VyIl0sInpvaWtvX2VudiI6ImRldiJ9.IrjkVX-8X-72kH2z8xjVJ4KBAmzdvxs5bEC3LjoGcW8",
  },
  {
    id: "admin",
    name: "Admin",
    title: "Platform Admin",
    company: "Zoiko Tech",
    avatar: "AD",
    color: "from-slate-600 to-slate-800",
    ring: "ring-slate-400",
    badge: "bg-slate-100 text-slate-700",
    description: "Full platform access including crypto audit, database, KMS and infrastructure.",
    capabilities: ["All analyst + manager rights", "Crypto & audit reports", "KMS / OPA / OIDC", "Database viewer"],
    jwt_sub: "admin@zoikotech.com",
    jwt: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbkB6b2lrb3RlY2guY29tIiwiaXNzIjoiaHR0cHM6Ly9hdXRoLnpvaWtvdGVjaC5jb20iLCJhdWQiOiJ6b2lrby1kZXYiLCJpYXQiOjE3Nzk3MDMyMTUsImV4cCI6MTc4MjI5NTIxNSwidGVuYW50X2lkIjoiMTExMTExMTEtMTExMS0xMTExLTExMTEtMTExMTExMTExMTExIiwicm9sZXMiOlsiYW5hbHlzdCIsIm1hbmFnZXIiLCJhZG1pbiJdLCJ6b2lrb19lbnYiOiJkZXYifQ.F6moZNwZTZXbHHTgXuK4ZVT3zKevEAeP7wF7gOCbdqc",
  },
];

const VALUE_PROPS = [
  { icon: Zap,        title: "AI-Powered Detection",    sub: "96% confidence on SC-001 overcharge patterns"          },
  { icon: Lock,       title: "8-Gate Execution",        sub: "Cryptographic + compliance gates before money moves"    },
  { icon: GitBranch,  title: "Immutable Audit Chain",   sub: "Ed25519 + Merkle WORM index — tamper-proof forever"     },
  { icon: BarChart3,  title: "Full Recovery Pipeline",  sub: "Ingest → Evidence → Governance → Execute → ACR"        },
];

export default function Login() {
  const nav = useNavigate();
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading]   = useState(false);

  function handleSignIn() {
    if (!selected) return;
    setLoading(true);
    const role = ROLES.find(r => r.id === selected)!;
    localStorage.setItem("zoiko_role",   role.id);
    localStorage.setItem("zoiko_user",   role.name);
    localStorage.setItem("zoiko_sub",    role.jwt_sub);
    localStorage.setItem("zoiko_tenant", TENANT_ID);
    localStorage.setItem("zoiko_jwt",    role.jwt);
    setTimeout(() => nav("/"), 700);
  }

  return (
    <div className="min-h-screen flex overflow-hidden">

      {/* ── Left brand panel ─────────────────────────────────────────────── */}
      <div className="hidden lg:flex lg:w-[44%] flex-col justify-between bg-[#0a0f1e] px-10 py-10 relative overflow-hidden">

        {/* Decorative circles */}
        <div className="absolute -top-32 -left-32 h-96 w-96 rounded-full bg-blue-600/10 blur-3xl pointer-events-none" />
        <div className="absolute bottom-0 right-0 h-80 w-80 rounded-full bg-violet-600/10 blur-3xl pointer-events-none" />
        <div className="absolute top-1/2 left-1/4 h-48 w-48 rounded-full bg-cyan-500/5 blur-2xl pointer-events-none" />

        {/* Logo */}
        <div className="relative z-10">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-blue-500 to-blue-700 flex items-center justify-center shadow-lg shadow-blue-500/30">
              <ShieldCheck className="h-5 w-5 text-white" />
            </div>
            <div>
              <p className="text-white font-bold text-lg tracking-wide leading-none">ZOIKO</p>
              <p className="text-blue-400 text-[11px] tracking-widest uppercase font-medium">AI Logistics</p>
            </div>
          </div>
        </div>

        {/* Hero copy */}
        <div className="relative z-10 space-y-6">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-blue-500/30 bg-blue-500/10 px-3 py-1 mb-5">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-[11px] text-blue-300 font-medium tracking-wide">SC-001 · Live Demo Environment</span>
            </div>
            <h1 className="text-4xl font-bold text-white leading-tight">
              Freight Audit &<br />
              <span className="bg-gradient-to-r from-blue-400 to-cyan-400 bg-clip-text text-transparent">
                Recovery Platform
              </span>
            </h1>
            <p className="mt-4 text-slate-400 text-sm leading-relaxed max-w-xs">
              Automatically detects overcharges, orchestrates two-human approval,
              and executes cryptographically auditable financial recovery.
            </p>
          </div>

          {/* Value props */}
          <div className="space-y-3">
            {VALUE_PROPS.map(({ icon: Icon, title, sub }) => (
              <div key={title} className="flex items-start gap-3">
                <div className="h-8 w-8 rounded-lg bg-white/5 border border-white/10 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <Icon className="h-4 w-4 text-blue-400" />
                </div>
                <div>
                  <p className="text-white text-sm font-semibold leading-tight">{title}</p>
                  <p className="text-slate-500 text-[11px] mt-0.5 leading-snug">{sub}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Scenario callout */}
        <div className="relative z-10 rounded-xl border border-white/8 bg-white/4 p-4">
          <p className="text-[10px] text-slate-500 uppercase tracking-widest font-semibold mb-2">Live Scenario — SC-001</p>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-white text-xs font-medium">BlueDart bills ₹12,500</p>
              <p className="text-slate-400 text-[11px]">Contract rate: ₹8,000</p>
            </div>
            <ChevronRight className="h-4 w-4 text-slate-600" />
            <div className="text-right">
              <p className="text-emerald-400 text-sm font-bold">₹4,500</p>
              <p className="text-slate-400 text-[11px]">Overcharge recovered</p>
            </div>
          </div>
        </div>
      </div>

      {/* ── Right sign-in panel ──────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col justify-center bg-slate-50 px-6 py-10 overflow-y-auto">
        <div className="w-full max-w-md mx-auto">

          {/* Mobile logo */}
          <div className="lg:hidden flex items-center gap-2.5 mb-8">
            <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-blue-500 to-blue-700 flex items-center justify-center">
              <ShieldCheck className="h-5 w-5 text-white" />
            </div>
            <div>
              <p className="font-bold text-slate-800">ZOIKO AI Logistics</p>
              <p className="text-[10px] text-slate-400">SC-001 Demo Environment</p>
            </div>
          </div>

          <div className="mb-8">
            <h2 className="text-2xl font-bold text-slate-800">Select your role</h2>
            <p className="text-slate-400 text-sm mt-1.5">
              Choose a persona to start the demo. Each role has different permissions.
            </p>
          </div>

          {/* Role cards */}
          <div className="space-y-3 mb-8">
            {ROLES.map(role => (
              <button
                key={role.id}
                onClick={() => setSelected(role.id)}
                className={cn(
                  "w-full text-left rounded-xl border-2 p-4 bg-white transition-all duration-150 shadow-sm",
                  selected === role.id
                    ? "border-blue-500 shadow-blue-100 shadow-md bg-blue-50/40"
                    : "border-slate-200 hover:border-slate-300 hover:shadow-md"
                )}
              >
                <div className="flex items-center gap-3">
                  <div className={cn(
                    "h-10 w-10 rounded-full bg-gradient-to-br flex items-center justify-center text-white font-bold text-sm flex-shrink-0",
                    role.color
                  )}>
                    {role.avatar}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="font-semibold text-slate-800 text-sm">{role.name}</p>
                      <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded-full", role.badge)}>
                        {role.id}
                      </span>
                    </div>
                    <p className="text-slate-400 text-xs">{role.title} · {role.company}</p>
                  </div>
                  <div className={cn(
                    "h-5 w-5 rounded-full border-2 flex items-center justify-center flex-shrink-0 transition-all",
                    selected === role.id
                      ? "border-blue-500 bg-blue-500"
                      : "border-slate-300"
                  )}>
                    {selected === role.id && <CheckCircle2 className="h-3.5 w-3.5 text-white" />}
                  </div>
                </div>

                {selected === role.id && (
                  <div className="mt-3 pt-3 border-t border-blue-100">
                    <p className="text-xs text-slate-500 mb-2 leading-relaxed">{role.description}</p>
                    <div className="flex flex-wrap gap-1.5">
                      {role.capabilities.map(c => (
                        <span key={c} className="text-[10px] bg-white border border-slate-200 rounded-md px-2 py-0.5 text-slate-600 font-medium">
                          {c}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </button>
            ))}
          </div>

          {/* Sign-in button */}
          <button
            disabled={!selected || loading}
            onClick={handleSignIn}
            className={cn(
              "w-full flex items-center justify-center gap-2.5 rounded-xl py-3.5 font-semibold text-sm transition-all duration-200",
              selected && !loading
                ? "bg-gradient-to-r from-blue-600 to-blue-700 text-white shadow-lg shadow-blue-500/25 hover:shadow-xl hover:shadow-blue-500/30 hover:-translate-y-0.5"
                : "bg-slate-200 text-slate-400 cursor-not-allowed"
            )}
          >
            {loading ? (
              <>
                <div className="h-4 w-4 rounded-full border-2 border-white/40 border-t-white animate-spin" />
                Signing in…
              </>
            ) : (
              <>
                Sign in as {ROLES.find(r => r.id === selected)?.name ?? "…"}
                <ArrowRight className="h-4 w-4" />
              </>
            )}
          </button>

          {/* Footer badges */}
          <div className="mt-8 flex items-center justify-center gap-6 flex-wrap">
            {[
              { icon: Lock,   label: "Ed25519 Signed"    },
              { icon: Award,  label: "SOC 2 Compliant"   },
              { icon: ShieldCheck, label: "OPA Enforced" },
            ].map(({ icon: Icon, label }) => (
              <div key={label} className="flex items-center gap-1.5 text-slate-400">
                <Icon className="h-3.5 w-3.5" />
                <span className="text-[11px] font-medium">{label}</span>
              </div>
            ))}
          </div>

          <p className="text-center text-slate-400 text-[11px] mt-4">
            {import.meta.env.VITE_USE_MOCK !== "false" ? "Mock mode" : "Live database"} ·
            Tenant: zoiko-demo · Phase 0–5 active
          </p>
        </div>
      </div>
    </div>
  );
}
