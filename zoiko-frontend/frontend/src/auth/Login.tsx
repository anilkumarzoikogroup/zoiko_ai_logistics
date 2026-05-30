import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ShieldCheck, Lock, Zap, GitBranch, BarChart3, Award, Eye, EyeOff } from "lucide-react";
import { cn } from "@/utils/cn";
import axios from "axios";

const API_BASE = (import.meta.env.VITE_API_BASE || "/api");

const VALUE_PROPS = [
  { icon: Zap,         title: "AI-Powered Detection",   sub: "96% confidence on freight overcharge patterns"       },
  { icon: Lock,        title: "8-Gate Execution",        sub: "Cryptographic + compliance gates before money moves" },
  { icon: GitBranch,   title: "Immutable Audit Chain",   sub: "Ed25519 + Merkle WORM index — tamper-proof forever"  },
  { icon: BarChart3,   title: "Full Recovery Pipeline",  sub: "Ingest → Evidence → Governance → Execute → ACR"     },
];

export default function Login() {
  const nav = useNavigate();

  const [email,    setEmail]    = useState("");
  const [password, setPassword] = useState("");
  const [showPw,   setShowPw]   = useState(false);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState("");

  async function handleSignIn(e: React.FormEvent) {
    e.preventDefault();
    if (!email || !password) return;
    setLoading(true);
    setError("");
    try {
      const { data } = await axios.post(`${API_BASE}/v1/auth/login`, { email, password });
      localStorage.setItem("zoiko_jwt",    data.token);
      localStorage.setItem("zoiko_tenant", data.tenant_id);
      localStorage.setItem("zoiko_role",   data.role);
      localStorage.setItem("zoiko_user",   data.full_name);
      localStorage.setItem("zoiko_sub",    data.email);
      nav("/");
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        const msg = err.response?.data?.detail;
        setError(typeof msg === "string" ? msg : "Login failed — check your credentials.");
      } else {
        setError("Could not reach the server. Make sure the backend is running.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex overflow-hidden">

      {/* ── Left brand panel ──────────────────────────────────────────────── */}
      <div className="hidden lg:flex lg:w-[44%] flex-col justify-between bg-[#0a0f1e] px-10 py-10 relative overflow-hidden">

        <div className="absolute -top-32 -left-32 h-96 w-96 rounded-full bg-blue-600/10 blur-3xl pointer-events-none" />
        <div className="absolute bottom-0 right-0 h-80 w-80 rounded-full bg-violet-600/10 blur-3xl pointer-events-none" />

        {/* Logo */}
        {/* Logo */}
        <div className="relative z-10">
          <img
            src="/logo-dark.jpg"
            alt="ZoikoAI"
            className="h-16 w-auto object-contain"
            onError={e => {
              const t = e.currentTarget;
              t.style.display = "none";
              const fallback = t.nextElementSibling as HTMLElement | null;
              if (fallback) fallback.style.display = "flex";
            }}
          />
          {/* Fallback if image not found */}
          <div className="hidden items-center gap-3">
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
              <span className="text-[11px] text-blue-300 font-medium tracking-wide">Freight Audit & Recovery Platform</span>
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

        {/* Platform tagline */}
        <div className="relative z-10 rounded-xl border border-white/8 bg-white/4 p-4">
          <p className="text-[10px] text-slate-500 uppercase tracking-widest font-semibold mb-1">Powered by</p>
          <p className="text-white text-xs font-medium">Zoiko AI Logistics Platform</p>
          <p className="text-slate-400 text-[11px] mt-0.5">Freight audit · Recovery · Cryptographic proof</p>
        </div>
      </div>

      {/* ── Right sign-in panel ───────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col justify-center bg-slate-50 px-6 py-10 overflow-y-auto">
        <div className="w-full max-w-md mx-auto">

          {/* Mobile logo */}
          <div className="lg:hidden mb-8">
            <img
              src="/logo-light.png"
              alt="ZoikoAI"
              className="h-12 w-auto object-contain"
              onError={e => {
                const t = e.currentTarget;
                t.style.display = "none";
                const fallback = t.nextElementSibling as HTMLElement | null;
                if (fallback) fallback.style.display = "flex";
              }}
            />
            <div className="hidden items-center gap-2.5">
              <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-blue-500 to-blue-700 flex items-center justify-center">
                <ShieldCheck className="h-5 w-5 text-white" />
              </div>
              <p className="font-bold text-slate-800">ZOIKO AI Logistics</p>
            </div>
          </div>

          <div className="mb-8">
            <h2 className="text-2xl font-bold text-slate-800">Sign in</h2>
            <p className="text-slate-400 text-sm mt-1.5">
              Enter your work email and password to access the platform.
            </p>
          </div>

          <form onSubmit={handleSignIn} className="space-y-4">

            {/* Email */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-slate-700" htmlFor="email">
                Work Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="you@company.com"
                className="w-full rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>

            {/* Password */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-slate-700" htmlFor="password">
                Password
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={showPw ? "text" : "password"}
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full rounded-lg border border-slate-200 bg-white px-4 py-2.5 pr-10 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                />
                <button
                  type="button"
                  onClick={() => setShowPw(v => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                  tabIndex={-1}
                >
                  {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            {/* Error */}
            {error && (
              <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-2.5 text-sm text-red-700">
                {error}
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={loading || !email || !password}
              className={cn(
                "w-full flex items-center justify-center gap-2.5 rounded-xl py-3.5 font-semibold text-sm transition-all duration-200 mt-2",
                !loading && email && password
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
                "Sign in"
              )}
            </button>
          </form>

          {/* Role info */}
          <div className="mt-8 rounded-xl border border-slate-200 bg-white p-4 space-y-2">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-widest">Access levels</p>
            <div className="space-y-1.5 text-xs text-slate-600">
              <p><span className="font-semibold text-blue-600">Analyst</span> — Reviews invoices, proposes recovery</p>
              <p><span className="font-semibold text-violet-600">Manager</span> — Approves / rejects recovery proposals</p>
              <p><span className="font-semibold text-slate-700">Admin</span> — Full access + user management</p>
            </div>
          </div>

          {/* Footer badges */}
          <div className="mt-6 flex items-center justify-center gap-6 flex-wrap">
            {[
              { icon: Lock,       label: "Ed25519 Signed"  },
              { icon: Award,      label: "SOC 2 Compliant" },
              { icon: ShieldCheck, label: "OPA Enforced"   },
            ].map(({ icon: Icon, label }) => (
              <div key={label} className="flex items-center gap-1.5 text-slate-400">
                <Icon className="h-3.5 w-3.5" />
                <span className="text-[11px] font-medium">{label}</span>
              </div>
            ))}
          </div>

          <p className="text-center text-slate-400 text-[11px] mt-4">
            {import.meta.env.VITE_USE_MOCK !== "false" ? "Mock mode" : "Live database"} · Zoiko AI Logistics
          </p>
        </div>
      </div>
    </div>
  );
}
