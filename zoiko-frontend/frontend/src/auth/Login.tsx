/**
 * Zoiko AI Enterprise Authentication
 * Implements spec v3.0 flows:
 *   Flow 1 — SSO Discovery (email-first)
 *   Flow 2 — Password Sign-In Fallback
 *   Flow 6 — Workspace Access Request
 *   Flow 7 — Credential Recovery
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Eye, EyeOff, ArrowLeft, ShieldCheck } from "lucide-react";
import { cn } from "@/utils/cn";
import axios from "axios";

const API = (import.meta.env.VITE_API_BASE || "/api");

// ── Design tokens from spec §6 ────────────────────────────────────────────────
// brand-navy: #0A1E3A  brand-teal: #00A6A6  action: #174EA6

type Flow = "discover" | "password" | "request" | "recovery" | "recovery-sent" | "request-sent";

// ── Left pane — Trust marks (spec §4.3) ───────────────────────────────────────
function TrustPane() {
  return (
    <div className="hidden lg:flex lg:w-[42%] flex-col justify-between px-10 py-10 relative overflow-hidden"
         style={{ background: "#0A1E3A" }}>
      <div className="absolute inset-0 opacity-5"
           style={{ backgroundImage: "radial-gradient(circle at 20% 80%, #00A6A6 0%, transparent 50%), radial-gradient(circle at 80% 20%, #174EA6 0%, transparent 50%)" }} />

      {/* Logo */}
      <div className="relative z-10">
        <img src="/logo-dark.jpg" alt="Zoiko AI" className="h-14 w-auto object-contain"
             onError={e => { e.currentTarget.style.display="none"; (e.currentTarget.nextElementSibling as HTMLElement|null)?.style?.removeProperty("display"); }} />
        <div style={{display:"none"}} className="flex flex-col">
          <span className="text-white font-bold text-xl tracking-tight">Zoiko AI</span>
          <span className="text-sm font-normal" style={{color:"#00A6A6"}}>Agentic Intelligence Platform</span>
        </div>
      </div>

      {/* Trust marks strip (spec §4.3) */}
      <div className="relative z-10 space-y-6">
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest mb-3" style={{color:"#667085"}}>Security & compliance</p>
          <div className="flex flex-wrap gap-2">
            {["SOC 2 Type II","ISO 27001","GDPR","CCPA","Data residency: US · EU · UK"].map(m => (
              <span key={m} className="text-[10px] font-medium px-2.5 py-1 rounded-md border"
                    style={{background:"rgba(255,255,255,0.05)", borderColor:"rgba(255,255,255,0.12)", color:"#94A3B8"}}>
                {m}
              </span>
            ))}
          </div>
        </div>

        <div className="border-t pt-5" style={{borderColor:"rgba(255,255,255,0.08)"}}>
          <p className="text-xs" style={{color:"#667085"}}>
            Governed agentic intelligence — every action cryptographically audited, every approval separation-of-duties enforced.
          </p>
        </div>

        <div className="flex items-center gap-1.5">
          <ShieldCheck className="h-3.5 w-3.5" style={{color:"#00A6A6"}} />
          <a href="#" className="text-[11px] font-medium hover:underline" style={{color:"#00A6A6"}}>
            Security & Trust Center
          </a>
        </div>
      </div>

      {/* Footer */}
      <div className="relative z-10">
        <p className="text-[10px]" style={{color:"#475569"}}>
          © 2026 Zoiko Group. All rights reserved.
        </p>
        <div className="flex gap-3 mt-1 flex-wrap">
          {["Security","Privacy","Terms","Acceptable Use","Status"].map(l => (
            <a key={l} href="#" className="text-[10px] hover:underline" style={{color:"#475569"}}>{l}</a>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Flow card wrapper ─────────────────────────────────────────────────────────
function FlowCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="w-full max-w-[440px] mx-auto">
      {/* Mobile logo */}
      <div className="lg:hidden mb-8">
        <img src="/logo-light.png" alt="Zoiko AI" className="h-10 w-auto object-contain"
             onError={e => { e.currentTarget.style.display="none"; }} />
      </div>
      {children}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export default function Login() {
  const nav = useNavigate();
  const [flow, setFlow]       = useState<Flow>("discover");
  const [email, setEmail]     = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw]   = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState("");

  // Workspace request form
  const [req, setReq] = useState({
    full_name:"", work_email:"", company_name:"", company_website:"",
    country:"", role:"", use_case:"", team_size:"", heard_from:"", consent: false,
  });

  // Recovery form
  const [recEmail, setRecEmail] = useState("");

  async function handleDiscover(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true); setError("");
    try {
      const { data } = await axios.post(`${API}/v1/auth/discover`, { email });
      if (data.route === "sso") {
        // SSO: in production redirect to IdP. For now show a message.
        setError(`Your organization uses SSO via ${data.idp_type}. Contact your IT administrator.`);
      } else {
        setFlow("password");
      }
    } catch (err: unknown) {
      const msg = axios.isAxiosError(err) ? err.response?.data?.detail : "Service unavailable";
      setError(typeof msg === "string" ? msg : "Service unavailable");
    } finally {
      setLoading(false);
    }
  }

  async function handlePassword(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true); setError("");
    try {
      const { data } = await axios.post(`${API}/v1/auth/login`, { email, password });
      localStorage.setItem("zoiko_jwt",    data.token);
      localStorage.setItem("zoiko_tenant", data.tenant_id);
      localStorage.setItem("zoiko_role",   data.role);
      localStorage.setItem("zoiko_user",   data.full_name);
      localStorage.setItem("zoiko_sub",    data.email);
      nav("/");
    } catch (err: unknown) {
      const msg = axios.isAxiosError(err) ? err.response?.data?.detail : null;
      setError(typeof msg === "string" ? msg : "Incorrect password. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  async function handleRecovery(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true); setError("");
    try {
      await axios.post(`${API}/v1/auth/recover/request`, { email: recEmail });
      setFlow("recovery-sent");
    } catch {
      // Always show same message — no enumeration
      setFlow("recovery-sent");
    } finally {
      setLoading(false);
    }
  }

  async function handleWorkspaceRequest(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true); setError("");
    try {
      await axios.post(`${API}/v1/auth/workspace-request`, req);
      setFlow("request-sent");
    } catch (err: unknown) {
      const msg = axios.isAxiosError(err) ? err.response?.data?.detail : null;
      setError(typeof msg === "string" ? msg : "Request failed. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  const btnClass = (disabled: boolean) => cn(
    "w-full flex items-center justify-center gap-2 rounded-xl py-3 text-sm font-semibold transition-all",
    disabled
      ? "bg-slate-200 text-slate-400 cursor-not-allowed"
      : "text-white hover:-translate-y-0.5 hover:shadow-md"
  );
  const inputClass = "w-full rounded-xl border px-4 py-3 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:border-transparent";

  return (
    <div className="min-h-screen flex overflow-hidden bg-slate-50">
      <TrustPane />

      {/* Right pane */}
      <div className="flex-1 flex flex-col justify-center px-6 py-10 overflow-y-auto">
        <FlowCard>

          {/* ── Flow 1: SSO Discovery ───────────────────────────────────── */}
          {flow === "discover" && (
            <form onSubmit={handleDiscover} className="space-y-5">
              <div>
                <h1 className="text-2xl font-semibold text-slate-900" style={{color:"#0A0E1A"}}>Sign in to Zoiko AI</h1>
                <p className="text-[15px] mt-1.5" style={{color:"#667085"}}>Use your work email to continue.</p>
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-slate-700" htmlFor="email">Work email</label>
                <input id="email" type="email" autoComplete="email" required
                       value={email} onChange={e => { setEmail(e.target.value); setError(""); }}
                       placeholder="name@company.com"
                       className={inputClass} style={{borderColor:"#D0D5DD"}} />
              </div>
              {error && <p className="text-sm rounded-lg px-4 py-2.5" style={{background:"#FEF3F2", color:"#B42318", border:"1px solid #FECDCA"}}>{error}</p>}
              <button type="submit" disabled={loading || !email}
                      className={btnClass(loading || !email)}
                      style={!loading && email ? {background:"#174EA6"} : {}}>
                {loading ? <><div className="h-4 w-4 rounded-full border-2 border-white/40 border-t-white animate-spin" />Checking…</> : "Continue"}
              </button>
              <div className="flex items-center justify-between pt-1">
                <button type="button" onClick={() => setFlow("request")}
                        className="text-sm hover:underline" style={{color:"#174EA6"}}>
                  Don't have access? Request a workspace
                </button>
              </div>
            </form>
          )}

          {/* ── Flow 2: Password Sign-In ────────────────────────────────── */}
          {flow === "password" && (
            <form onSubmit={handlePassword} className="space-y-5">
              <div>
                <button type="button" onClick={() => { setFlow("discover"); setError(""); }}
                        className="flex items-center gap-1.5 text-sm mb-4 hover:underline" style={{color:"#667085"}}>
                  <ArrowLeft className="h-3.5 w-3.5" /> Use different email
                </button>
                <h1 className="text-2xl font-semibold" style={{color:"#0A0E1A"}}>Enter your password</h1>
                <p className="text-[15px] mt-1.5" style={{color:"#667085"}}>Signed in as <span className="font-medium text-slate-700">{email}</span></p>
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-slate-700" htmlFor="password">Password</label>
                <div className="relative">
                  <input id="password" type={showPw ? "text" : "password"} autoComplete="current-password" required
                         value={password} onChange={e => { setPassword(e.target.value); setError(""); }}
                         placeholder="••••••••" className={cn(inputClass, "pr-10")} style={{borderColor:"#D0D5DD"}} />
                  <button type="button" onClick={() => setShowPw(v => !v)} tabIndex={-1}
                          className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">
                    {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>
              {error && <p className="text-sm rounded-lg px-4 py-2.5" style={{background:"#FEF3F2", color:"#B42318", border:"1px solid #FECDCA"}}>{error}</p>}
              <button type="submit" disabled={loading || !password}
                      className={btnClass(loading || !password)}
                      style={!loading && password ? {background:"#174EA6"} : {}}>
                {loading ? <><div className="h-4 w-4 rounded-full border-2 border-white/40 border-t-white animate-spin" />Signing in…</> : "Sign in"}
              </button>
              <div className="text-center">
                <button type="button" onClick={() => { setRecEmail(email); setFlow("recovery"); setError(""); }}
                        className="text-sm hover:underline" style={{color:"#667085"}}>
                  Forgot password?
                </button>
              </div>
            </form>
          )}

          {/* ── Flow 7: Credential Recovery ────────────────────────────── */}
          {flow === "recovery" && (
            <form onSubmit={handleRecovery} className="space-y-5">
              <div>
                <button type="button" onClick={() => { setFlow("password"); setError(""); }}
                        className="flex items-center gap-1.5 text-sm mb-4 hover:underline" style={{color:"#667085"}}>
                  <ArrowLeft className="h-3.5 w-3.5" /> Return to sign in
                </button>
                <h1 className="text-2xl font-semibold" style={{color:"#0A0E1A"}}>Reset your password</h1>
                <p className="text-[15px] mt-1.5" style={{color:"#667085"}}>
                  Enter your work email. If we find an account, we'll send recovery instructions.
                </p>
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-slate-700" htmlFor="rec-email">Work email</label>
                <input id="rec-email" type="email" autoComplete="email" required
                       value={recEmail} onChange={e => setRecEmail(e.target.value)}
                       placeholder="name@company.com"
                       className={inputClass} style={{borderColor:"#D0D5DD"}} />
              </div>
              <button type="submit" disabled={loading || !recEmail}
                      className={btnClass(loading || !recEmail)}
                      style={!loading && recEmail ? {background:"#174EA6"} : {}}>
                {loading ? <><div className="h-4 w-4 rounded-full border-2 border-white/40 border-t-white animate-spin" />Sending…</> : "Send instructions"}
              </button>
            </form>
          )}

          {flow === "recovery-sent" && (
            <div className="space-y-5">
              <div className="rounded-xl p-4" style={{background:"#F0FDF4", border:"1px solid #A7F3D0"}}>
                <p className="text-sm font-semibold" style={{color:"#027A48"}}>Instructions on their way</p>
                <p className="text-sm mt-1" style={{color:"#065F46"}}>
                  If an account exists for this email, instructions are on their way. Check your inbox.
                </p>
              </div>
              <button type="button" onClick={() => { setFlow("discover"); setError(""); setRecEmail(""); }}
                      className="text-sm hover:underline" style={{color:"#174EA6"}}>
                Return to sign in
              </button>
            </div>
          )}

          {/* ── Flow 6: Workspace Access Request ───────────────────────── */}
          {flow === "request" && (
            <form onSubmit={handleWorkspaceRequest} className="space-y-4">
              <div>
                <button type="button" onClick={() => { setFlow("discover"); setError(""); }}
                        className="flex items-center gap-1.5 text-sm mb-4 hover:underline" style={{color:"#667085"}}>
                  <ArrowLeft className="h-3.5 w-3.5" /> Back to sign in
                </button>
                <h1 className="text-2xl font-semibold" style={{color:"#0A0E1A"}}>Request access to Zoiko AI</h1>
                <p className="text-[15px] mt-1.5" style={{color:"#667085"}}>
                  Tell us about your organization. A Zoiko representative will follow up within one business day.
                </p>
              </div>

              <div className="grid grid-cols-2 gap-3">
                {[
                  {id:"full_name",    label:"Full name",       type:"text",  ph:"Your full name",     half:true},
                  {id:"work_email",   label:"Work email",      type:"email", ph:"name@company.com",   half:true},
                  {id:"company_name", label:"Company name",    type:"text",  ph:"Acme Inc.",           half:true},
                  {id:"company_website",label:"Company website",type:"url",  ph:"https://acme.com",   half:true},
                ].map(f => (
                  <div key={f.id} className={cn("space-y-1", f.half ? "" : "col-span-2")}>
                    <label className="text-xs font-medium text-slate-600">{f.label}</label>
                    <input type={f.type} required={["full_name","work_email","company_name"].includes(f.id)}
                           placeholder={f.ph} value={(req as any)[f.id]}
                           onChange={e => setReq(r => ({...r, [f.id]: e.target.value}))}
                           className={inputClass} style={{borderColor:"#D0D5DD", fontSize:"14px", padding:"10px 14px"}} />
                  </div>
                ))}
              </div>

              <div className="grid grid-cols-2 gap-3">
                {[
                  {id:"country",    label:"Country / Region",  opts:["United States","United Kingdom","India","Germany","France","Singapore","Australia","Other"]},
                  {id:"team_size",  label:"Estimated team size", opts:["1–10","11–50","51–200","201–1000","1000+"]},
                  {id:"role",       label:"Your role",           opts:["Executive / C-Suite","Director / VP","Manager","Individual contributor","Other"]},
                  {id:"use_case",   label:"Primary use case",    opts:["Freight audit","Contract management","Compliance","Other"]},
                ].map(f => (
                  <div key={f.id} className="space-y-1">
                    <label className="text-xs font-medium text-slate-600">{f.label}</label>
                    <select value={(req as any)[f.id]} onChange={e => setReq(r => ({...r, [f.id]: e.target.value}))}
                            className={inputClass} style={{borderColor:"#D0D5DD", fontSize:"14px", padding:"10px 14px"}}>
                      <option value="">Select…</option>
                      {f.opts.map(o => <option key={o} value={o}>{o}</option>)}
                    </select>
                  </div>
                ))}
              </div>

              {/* Privacy consent */}
              <div className="flex items-start gap-3 rounded-xl p-3" style={{background:"#F8FAFC", border:"1px solid #E2E8F0"}}>
                <input type="checkbox" id="consent" checked={req.consent}
                       onChange={e => setReq(r => ({...r, consent: e.target.checked}))}
                       className="mt-0.5 h-4 w-4 rounded flex-shrink-0" />
                <label htmlFor="consent" className="text-xs leading-relaxed" style={{color:"#667085"}}>
                  I agree that Zoiko may contact me about my request and process my information under the{" "}
                  <a href="#" className="underline" style={{color:"#174EA6"}}>Privacy Notice</a>.
                </label>
              </div>

              {error && <p className="text-sm rounded-lg px-4 py-2.5" style={{background:"#FEF3F2", color:"#B42318", border:"1px solid #FECDCA"}}>{error}</p>}

              <button type="submit"
                      disabled={loading || !req.full_name || !req.work_email || !req.company_name || !req.consent}
                      className={btnClass(loading || !req.full_name || !req.work_email || !req.company_name || !req.consent)}
                      style={!loading && req.full_name && req.work_email && req.company_name && req.consent ? {background:"#174EA6"} : {}}>
                {loading ? <><div className="h-4 w-4 rounded-full border-2 border-white/40 border-t-white animate-spin" />Submitting…</> : "Request access"}
              </button>
            </form>
          )}

          {flow === "request-sent" && (
            <div className="space-y-5">
              <h1 className="text-2xl font-semibold" style={{color:"#0A0E1A"}}>Request received</h1>
              <div className="rounded-xl p-4" style={{background:"#F0FDF4", border:"1px solid #A7F3D0"}}>
                <p className="text-sm font-semibold" style={{color:"#027A48"}}>We'll be in touch</p>
                <p className="text-sm mt-1" style={{color:"#065F46"}}>
                  A Zoiko representative will follow up within one business day.
                </p>
              </div>
              <button type="button" onClick={() => { setFlow("discover"); setError(""); }}
                      className="text-sm hover:underline" style={{color:"#174EA6"}}>
                Return to sign in
              </button>
            </div>
          )}

          {/* Footer */}
          <div className="mt-8 pt-6 border-t flex flex-wrap gap-3 justify-center" style={{borderColor:"#E2E8F0"}}>
            {["Security","Privacy","Terms","Contact"].map(l => (
              <a key={l} href="#" className="text-[11px] hover:underline" style={{color:"#94A3B8"}}>{l}</a>
            ))}
          </div>
        </FlowCard>
      </div>
    </div>
  );
}
