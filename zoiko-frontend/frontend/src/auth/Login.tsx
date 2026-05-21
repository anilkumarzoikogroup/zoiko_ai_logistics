import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ShieldCheck, UserCheck, CheckCircle2, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/utils/cn";

const ROLES = [
  {
    id: "analyst",
    name: "Ravi Kumar",
    title: "Freight Analyst",
    company: "Amazon India",
    avatar: "RK",
    color: "bg-zoiko-blue",
    description: "Reviews flagged invoices, runs AI analysis, proposes recovery actions.",
    capabilities: ["View all cases", "Propose recovery", "Add evidence", "View findings"],
    jwt_sub: "ravi@amazon.com",
  },
  {
    id: "manager",
    name: "Ramu Sharma",
    title: "Finance Manager",
    company: "Amazon India",
    avatar: "RS",
    color: "bg-zoiko-purple",
    description: "Final approver for recovery decisions. Cannot approve own proposals (SoD).",
    capabilities: ["Approve / Reject proposals", "View audit trail", "View tokens", "Execute recovery"],
    jwt_sub: "ramu@amazon.com",
  },
  {
    id: "admin",
    name: "Admin",
    title: "Platform Admin",
    company: "Zoiko Tech",
    avatar: "AD",
    color: "bg-zoiko-navy",
    description: "Full access to all phases, crypto audit, database, and infrastructure.",
    capabilities: ["All analyst + manager rights", "Crypto & audit", "KMS / OIDC / OPA", "Database viewer"],
    jwt_sub: "admin@zoikotech.com",
  },
];

export default function Login() {
  const nav = useNavigate();
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function handleSignIn() {
    if (!selected) return;
    setLoading(true);
    const role = ROLES.find(r => r.id === selected)!;
    localStorage.setItem("zoiko_role", role.id);
    localStorage.setItem("zoiko_user", role.name);
    localStorage.setItem("zoiko_sub", role.jwt_sub);
    localStorage.setItem("zoiko_tenant", "amazon-india");
    setTimeout(() => nav("/"), 600);
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-zoiko-navy via-zoiko-blue to-zoiko-teal flex items-center justify-center p-4">
      <div className="w-full max-w-3xl">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center h-14 w-14 rounded-2xl bg-white/10 backdrop-blur mb-4">
            <ShieldCheck className="h-7 w-7 text-white" />
          </div>
          <h1 className="text-3xl font-bold text-white">Zoiko AI Logistics</h1>
          <p className="text-white/70 mt-2 text-sm">
            Freight Dispute Resolution · SC-001 · Cryptographically auditable
          </p>
        </div>

        {/* Role cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          {ROLES.map(role => (
            <button
              key={role.id}
              onClick={() => setSelected(role.id)}
              className={cn(
                "text-left rounded-xl border-2 p-5 bg-white/10 backdrop-blur transition-all duration-150",
                selected === role.id
                  ? "border-white bg-white/20 scale-[1.02] shadow-lg"
                  : "border-white/20 hover:border-white/60 hover:bg-white/15"
              )}
            >
              <div className="flex items-center gap-3 mb-3">
                <div className={cn("h-10 w-10 rounded-full flex items-center justify-center text-white font-bold text-sm", role.color)}>
                  {role.avatar}
                </div>
                <div>
                  <p className="font-semibold text-white text-sm">{role.name}</p>
                  <p className="text-white/60 text-xs">{role.title}</p>
                </div>
                {selected === role.id && (
                  <CheckCircle2 className="h-5 w-5 text-white ml-auto flex-shrink-0" />
                )}
              </div>
              <p className="text-white/75 text-xs mb-3 leading-relaxed">{role.description}</p>
              <ul className="space-y-1">
                {role.capabilities.map(c => (
                  <li key={c} className="flex items-center gap-1.5 text-xs text-white/60">
                    <span className="h-1 w-1 rounded-full bg-white/40 flex-shrink-0" />
                    {c}
                  </li>
                ))}
              </ul>
            </button>
          ))}
        </div>

        {/* Sign-in button */}
        <div className="flex justify-center">
          <Button
            size="lg"
            disabled={!selected || loading}
            onClick={handleSignIn}
            className="bg-white text-zoiko-navy hover:bg-white/90 font-semibold px-8 gap-2 disabled:opacity-40"
          >
            {loading ? (
              <>
                <div className="h-4 w-4 rounded-full border-2 border-zoiko-navy border-t-transparent animate-spin" />
                Signing in…
              </>
            ) : (
              <>
                Sign in as {ROLES.find(r => r.id === selected)?.name ?? "…"}
                <ArrowRight className="h-4 w-4" />
              </>
            )}
          </Button>
        </div>

        {/* Footer note */}
        <p className="text-center text-white/40 text-xs mt-6">
          Demo environment · Tenant: amazon-india · {import.meta.env.VITE_USE_MOCK !== "false" ? "Mock data" : "Live DB"}
        </p>
      </div>
    </div>
  );
}
