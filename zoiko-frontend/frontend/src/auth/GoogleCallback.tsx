import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useAppDispatch } from "@/store";
import { login as loginAction } from "@/store/authSlice";
import axios from "axios";
import { Building2, UserPlus } from "lucide-react";

const API          = import.meta.env.VITE_API_BASE || "/api";
const REDIRECT_URI = `${window.location.origin}/auth/google/callback`;

type Stage = "loading" | "org-form" | "error";

function GoogleIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" style={{ flexShrink: 0 }}>
      <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
      <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
      <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
      <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
    </svg>
  );
}

export default function GoogleCallback() {
  const nav      = useNavigate();
  const dispatch = useAppDispatch();
  const called   = useRef(false);

  const [stage,       setStage]       = useState<Stage>("loading");
  const [error,       setError]       = useState("");
  const [signupToken, setSignupToken] = useState("");
  const [googleName,  setGoogleName]  = useState("");
  const [googleEmail, setGoogleEmail] = useState("");
  const [orgName,     setOrgName]     = useState("");
  const [submitting,  setSubmitting]  = useState(false);

  useEffect(() => {
    if (called.current) return;
    called.current = true;

    const params      = new URLSearchParams(window.location.search);
    const code        = params.get("code");
    const googleError = params.get("error");

    if (googleError || !code) {
      nav("/login?error=google_cancelled");
      return;
    }

    axios
      .post(`${API}/v1/auth/google/callback`, { code, redirect_uri: REDIRECT_URI }, { validateStatus: s => s < 500 })
      .then(({ data, status }) => {
        if (status === 200 || status === 201) {
          dispatch(loginAction({
            token:    data.token,
            tenantId: data.tenant_id,
            role:     data.role,
            user:     data.full_name,
            sub:      data.email,
          }));
          nav("/");
        } else if (status === 202 && data.status === "new_user") {
          setGoogleName(data.name);
          setGoogleEmail(data.email);
          setSignupToken(data.signup_token);
          setStage("org-form");
        } else {
          setError(data.detail || "Google sign-in failed.");
          setStage("error");
        }
      })
      .catch(() => { setError("Could not connect to server."); setStage("error"); });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleSignup(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const { data } = await axios.post(`${API}/v1/auth/google/complete-signup`, {
        signup_token: signupToken,
        org_name:     orgName,
      });
      dispatch(loginAction({
        token:    data.token,
        tenantId: data.tenant_id,
        role:     data.role,
        user:     data.full_name,
        sub:      data.email,
      }));
      nav("/");
    } catch (err: unknown) {
      const msg = axios.isAxiosError(err) ? err.response?.data?.detail : null;
      setError(typeof msg === "string" ? msg : "Registration failed. Please try again.");
      setSubmitting(false);
    }
  }

  // ── Loading ──────────────────────────────────────────────────────────────────
  if (stage === "loading") return (
    <div style={{ display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center", height:"100vh", background:"linear-gradient(145deg,#03071a,#080f28,#0b1a3a)", gap:"16px" }}>
      <div style={{ width:"44px", height:"44px", borderRadius:"50%", border:"3px solid rgba(255,255,255,0.1)", borderTop:"3px solid #60A5FA", animation:"spin 0.8s linear infinite" }}/>
      <p style={{ color:"#94A3B8", fontSize:"14px", margin:0 }}>Signing in with Google…</p>
      <style>{`@keyframes spin { to { transform:rotate(360deg); } }`}</style>
    </div>
  );

  // ── Error ────────────────────────────────────────────────────────────────────
  if (stage === "error") return (
    <div style={{ display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center", height:"100vh", background:"linear-gradient(145deg,#03071a,#080f28,#0b1a3a)", gap:"12px" }}>
      <p style={{ color:"#F87171", fontSize:"14px", margin:0 }}>{error}</p>
      <button onClick={() => nav("/login")}
              style={{ color:"#60A5FA", background:"none", border:"none", cursor:"pointer", fontSize:"14px" }}>
        ← Back to login
      </button>
    </div>
  );

  // ── Org-name form (new user) ─────────────────────────────────────────────────
  return (
    <div style={{ display:"flex", alignItems:"center", justifyContent:"center", height:"100vh", background:"linear-gradient(145deg,#03071a,#080f28,#0b1a3a)" }}>
      <div style={{ width:"400px", background:"#1E293B", borderRadius:"24px", overflow:"hidden", boxShadow:"0 32px 80px rgba(0,0,0,0.5),0 0 0 1px rgba(255,255,255,0.12)" }}>

        {/* Rainbow strip */}
        <div style={{ height:"4px", background:"linear-gradient(90deg,#2563EB,#60A5FA,#34D399,#A78BFA,#F472B6)" }}/>

        <div style={{ padding:"28px" }}>
          {/* Google account badge — shows name + email from Google */}
          <div style={{ display:"flex", alignItems:"center", gap:"12px", marginBottom:"20px", padding:"12px 14px", borderRadius:"12px", background:"rgba(66,133,244,0.1)", border:"1px solid rgba(66,133,244,0.25)" }}>
            <GoogleIcon/>
            <div>
              <p style={{ color:"#F1F5F9", fontSize:"14px", fontWeight:700, margin:0 }}>{googleName}</p>
              <p style={{ color:"#64748B", fontSize:"12px", margin:"2px 0 0" }}>{googleEmail}</p>
            </div>
          </div>

          <h2 style={{ fontSize:"22px", fontWeight:900, color:"#F1F5F9", margin:"0 0 4px" }}>
            Create Your Organization
          </h2>
          <p style={{ color:"#94A3B8", fontSize:"13px", marginBottom:"20px" }}>
            One last step — give your workspace a name.
          </p>

          <form onSubmit={handleSignup} style={{ display:"flex", flexDirection:"column", gap:"12px" }}>
            <div>
              <label style={{ fontSize:"10px", fontWeight:700, color:"#64748B", letterSpacing:"0.1em", display:"block", marginBottom:"6px" }}>
                ORGANIZATION NAME
              </label>
              <div style={{ position:"relative" }}>
                <div style={{ position:"absolute", left:"12px", top:"50%", transform:"translateY(-50%)", width:"26px", height:"26px", borderRadius:"7px", background:"rgba(100,116,139,0.08)", display:"flex", alignItems:"center", justifyContent:"center" }}>
                  <Building2 size={13} color="#94A3B8"/>
                </div>
                <input
                  type="text" required
                  placeholder="e.g. Amazon India"
                  value={orgName}
                  onChange={e => { setOrgName(e.target.value); setError(""); }}
                  style={{ width:"100%", borderRadius:"12px", border:`1.5px solid ${orgName ? "#93C5FD" : "rgba(255,255,255,0.1)"}`, background: orgName ? "#1a2744" : "#0F172A", padding:"11px 16px 11px 46px", fontSize:"14px", color:"#F1F5F9", outline:"none", boxSizing:"border-box", transition:"all .2s" }}
                />
              </div>
            </div>

            {error && (
              <div style={{ borderRadius:"10px", padding:"10px 14px", background:"#FEF2F2", color:"#DC2626", fontSize:"12px", border:"1px solid #FECACA" }}>
                {error}
              </div>
            )}

            <button type="submit" disabled={submitting || !orgName}
                    style={{ width:"100%", borderRadius:"12px", padding:"14px", fontSize:"14px", fontWeight:700, color:"white", border:"none", cursor: submitting||!orgName ? "not-allowed" : "pointer", background: submitting||!orgName ? "#93C5FD" : "linear-gradient(135deg,#1D4ED8,#3B82F6)", boxShadow:"0 8px 24px rgba(37,99,235,0.35)", display:"flex", alignItems:"center", justifyContent:"center", gap:"8px" }}>
              {submitting
                ? <><div style={{ width:"16px", height:"16px", borderRadius:"50%", border:"2px solid rgba(255,255,255,0.4)", borderTop:"2px solid white", animation:"spin 0.7s linear infinite" }}/> Creating account…</>
                : <><UserPlus size={15}/> Create Account</>
              }
            </button>
          </form>
        </div>
      </div>
      <style>{`@keyframes spin { to { transform:rotate(360deg); } }`}</style>
    </div>
  );
}
