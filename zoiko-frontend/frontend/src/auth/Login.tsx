import { useState, useEffect } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAppDispatch } from "@/store";
import { login as loginAction } from "@/store/authSlice";
import {
  Eye, EyeOff, Mail, Lock, Shield, FileText, BarChart2, Rocket,
  Users, ArrowLeft, CheckCircle2, Moon, Sun, ShieldCheck, Zap, Globe,
  UserPlus, Building2,
} from "lucide-react";
import axios from "axios";

const API = import.meta.env.VITE_API_BASE || "/api";
type Flow = "login" | "recovery" | "recovery-sent" | "register" | "register-sent";

const FEATURES = [
  { icon: Shield,    color: "#60A5FA", title: "AI-Powered Validation",   desc: "Intelligent checks and risk detection"        },
  { icon: FileText,  color: "#34D399", title: "Audit & Compliance",       desc: "End-to-end audit trail and governance"        },
  { icon: BarChart2, color: "#A78BFA", title: "Reconciliation",           desc: "Automated matching and discrepancy detection" },
  { icon: Rocket,    color: "#F472B6", title: "Execution Excellence",     desc: "From insight to action with confidence"       },
];

const STATS = [
  { value: "100K+", label: "Shipments Processed", color: "#60A5FA" },
  { value: "99.9%", label: "Data Accuracy",       color: "#34D399" },
  { value: "24/7",  label: "AI Monitoring",       color: "#A78BFA" },
  { value: "50+",   label: "Enterprises",         color: "#F472B6" },
];

// Google G SVG — fixed size, no Tailwind classes
function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style={{flexShrink:0}}>
      <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
      <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
      <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
      <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
    </svg>
  );
}

export default function Login() {
  const nav      = useNavigate();
  const dispatch = useAppDispatch();
  const [flow, setFlow]         = useState<Flow>("login");
  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw]     = useState(false);
  const [remember, setRemember] = useState(false);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState("");
  const [recEmail, setRecEmail]   = useState("");
  const [dark, setDark]           = useState(true);
  const [reg, setReg]             = useState({ org:"", name:"", email:"", password:"" });

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault(); setLoading(true); setError("");
    try {
      const { data } = await axios.post(`${API}/v1/auth/org-signup`, {
        org_name:       reg.org,
        admin_name:     reg.name,
        admin_email:    reg.email,
        admin_password: reg.password,
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
    } finally { setLoading(false); }
  }
  const [time, setTime]         = useState(new Date());

  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault(); setLoading(true); setError("");
    try {
      const { data } = await axios.post(`${API}/v1/auth/login`, { email, password });
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
      setError(typeof msg === "string" ? msg : "Invalid email or password.");
    } finally { setLoading(false); }
  }

  async function handleRecovery(e: React.FormEvent) {
    e.preventDefault(); setLoading(true);
    try { await axios.post(`${API}/v1/auth/recover/request`, { email: recEmail }); } catch { /**/ }
    finally { setLoading(false); setFlow("recovery-sent"); setError(""); }
  }

  function handleGoogle() {
    setError("Google SSO activates after GCP deployment. Use email & password for now.");
  }

  // Dark mode theme values
  const card    = dark ? { bg:"#1E293B", border:"rgba(255,255,255,0.08)", heading:"#F1F5F9", sub:"#94A3B8", label:"#64748B", foot:"#0F172A", footBorder:"rgba(255,255,255,0.06)" }
                       : { bg:"#FFFFFF",  border:"rgba(0,0,0,0.06)",       heading:"#0F172A", sub:"#94A3B8",  label:"#64748B", foot:"#F8FAFC", footBorder:"#F1F5F9" };
  const inp     = dark ? { border:"rgba(255,255,255,0.1)", activeBorder:"#93C5FD", bg:"#0F172A",  activeBg:"#1a2744", text:"#F1F5F9"  }
                       : { border:"#E2E8F0",                activeBorder:"#93C5FD", bg:"#FFFFFF",  activeBg:"#FAFCFF", text:"#1E293B"  };
  const secBadge = dark ? { bg:"rgba(255,255,255,0.05)", border:"rgba(255,255,255,0.08)" }
                        : { bg:"#F8FAFC",                  border:"#F1F5F9" };

  const inputStyle = (active: boolean): React.CSSProperties => ({
    width:"100%", borderRadius:"12px",
    border: `1.5px solid ${active ? inp.activeBorder : inp.border}`,
    boxShadow: active ? "0 0 0 3px rgba(37,99,235,0.08)" : "none",
    background: active ? inp.activeBg : inp.bg,
    padding: "11px 16px 11px 48px",
    fontSize: "14px", color: inp.text, outline: "none", transition: "all .2s",
  });

  return (
    <div style={{height:"100vh",width:"100vw",overflow:"hidden",display:"flex",flexDirection:"column",position:"relative"}}>

      {/* ── Background ─────────────────────────────────────────────── */}
      <div style={{position:"absolute",inset:0,zIndex:0,background:"linear-gradient(145deg,#03071a 0%,#080f28 35%,#0b1a3a 65%,#060d1e 100%)"}} />
      <div style={{position:"absolute",inset:0,zIndex:0,backgroundImage:"url('/bg-logistics.png')",backgroundSize:"cover",backgroundPosition:"center 40%",opacity:0.45}} />
      <div style={{position:"absolute",inset:0,zIndex:0,background:"linear-gradient(to right,rgba(3,7,26,.6) 0%,rgba(3,7,26,.2) 45%,rgba(3,7,26,.9) 72%,rgba(3,7,26,.98) 100%)"}} />
      {/* Glow orbs */}
      <div style={{position:"absolute",top:"-10%",left:"-5%",width:"500px",height:"500px",borderRadius:"50%",filter:"blur(100px)",background:"radial-gradient(circle,rgba(29,78,216,.4) 0%,transparent 70%)",zIndex:0,pointerEvents:"none",animation:"pulse 4s ease-in-out infinite"}} />
      <div style={{position:"absolute",bottom:"-10%",left:"20%",width:"400px",height:"400px",borderRadius:"50%",filter:"blur(80px)",background:"radial-gradient(circle,rgba(14,165,233,.3) 0%,transparent 70%)",zIndex:0,pointerEvents:"none",animation:"pulse 6s ease-in-out infinite"}} />
      {/* Dot grid */}
      <div style={{position:"absolute",inset:0,zIndex:0,opacity:0.08,backgroundImage:"radial-gradient(circle,rgba(255,255,255,.5) 1px,transparent 1px)",backgroundSize:"28px 28px",pointerEvents:"none"}} />

      {/* ── All content ────────────────────────────────────────────── */}
      <div style={{position:"relative",zIndex:10,display:"flex",flexDirection:"column",height:"100%"}}>

        {/* Top bar */}
        <div style={{flexShrink:0,display:"flex",alignItems:"center",justifyContent:"space-between",padding:"14px 40px"}}>

          {/* Logo — BIG */}
          <div style={{display:"flex",alignItems:"center",gap:"12px"}}>
            <img src="/logo-dark.jpg" alt="ZoikoAI"
                 style={{height:"64px",width:"auto",objectFit:"contain",filter:"drop-shadow(0 4px 12px rgba(96,165,250,0.3))"}}
                 onError={e => {
                   e.currentTarget.style.display = "none";
                   const fb = e.currentTarget.nextElementSibling as HTMLElement | null;
                   if (fb) fb.style.display = "flex";
                 }} />
            {/* Text fallback — always nice-looking */}
            <div style={{display:"flex",flexDirection:"column"}}>
              <div style={{display:"flex",alignItems:"baseline",gap:"2px"}}>
                <span style={{color:"white",fontSize:"28px",fontWeight:900,lineHeight:1,letterSpacing:"-0.5px"}}>Zoiko</span>
                <span style={{fontSize:"28px",fontWeight:900,lineHeight:1,background:"linear-gradient(90deg,#60A5FA,#34D399)",WebkitBackgroundClip:"text",WebkitTextFillColor:"transparent"}}>AI</span>
                <sup style={{color:"white",fontSize:"10px",marginBottom:"4px"}}>™</sup>
              </div>
              <span style={{fontSize:"10px",fontWeight:700,letterSpacing:"0.2em",color:"#60A5FA"}}>AI LOGISTICS</span>
            </div>
          </div>

          {/* Right utilities */}
          <div style={{display:"flex",alignItems:"center",gap:"10px"}}>
            <div style={{display:"flex",alignItems:"center",gap:"6px",padding:"6px 12px",borderRadius:"20px",background:"rgba(255,255,255,0.05)",border:"1px solid rgba(255,255,255,0.1)",color:"#94A3B8",fontSize:"11px",fontFamily:"monospace"}}>
              <span style={{width:"6px",height:"6px",borderRadius:"50%",background:"#34D399",display:"inline-block",animation:"pulse 2s infinite"}} />
              {time.toLocaleTimeString()}
            </div>
            <div style={{display:"flex",alignItems:"center",gap:"6px",padding:"6px 12px",borderRadius:"20px",background:"rgba(52,211,153,0.1)",border:"1px solid rgba(52,211,153,0.2)",color:"#34D399",fontSize:"11px",fontWeight:600}}>
              <Globe size={12} /> System Operational
            </div>
            <button onClick={() => setDark(v=>!v)} style={{display:"flex",alignItems:"center",gap:"8px",padding:"8px 16px",borderRadius:"20px",background:"rgba(255,255,255,0.07)",border:"1px solid rgba(255,255,255,0.15)",color:"white",fontSize:"13px",fontWeight:600,cursor:"pointer"}}>
              {dark ? <Moon size={14}/> : <Sun size={14}/>}
              {dark ? "Dark Mode" : "Light Mode"}
            </button>
          </div>
        </div>

        {/* Main content */}
        <div style={{flex:1,display:"flex",alignItems:"center",padding:"0 40px",gap:"32px",minHeight:0,paddingBottom:"8px",justifyContent:"space-between"}}>

          {/* LEFT — always visible, min width enforced */}
          <div style={{flex:"1 1 0",minWidth:"360px",maxWidth:"520px",display:"flex",flexDirection:"column",height:"100%",justifyContent:"space-between",paddingBottom:"8px"}}>
            <div>
              {/* Badge */}
              <div style={{display:"inline-flex",alignItems:"center",gap:"8px",padding:"6px 14px",borderRadius:"20px",background:"rgba(96,165,250,0.1)",border:"1px solid rgba(96,165,250,0.25)",marginBottom:"20px"}}>
                <Zap size={12} color="#60A5FA"/>
                <span style={{color:"#60A5FA",fontSize:"11px",fontWeight:700,letterSpacing:"0.15em"}}>GOVERNED AUTONOMOUS</span>
              </div>

              {/* Headline */}
              <h1 style={{color:"white",fontSize:"52px",fontWeight:900,lineHeight:1.1,margin:0}}>
                Intelligent<br/>Logistics.
              </h1>
              <h1 style={{fontSize:"52px",fontWeight:900,lineHeight:1.1,margin:"4px 0 0",background:"linear-gradient(90deg,#60A5FA,#34D399,#A78BFA)",WebkitBackgroundClip:"text",WebkitTextFillColor:"transparent"}}>
                Assured Trust.
              </h1>
              <div style={{display:"flex",gap:"4px",marginTop:"10px"}}>
                {["#60A5FA","#34D399","#A78BFA"].map((c,i)=>(
                  <div key={i} style={{height:"4px",borderRadius:"2px",background:c,width:i===0?"36px":"14px"}}/>
                ))}
              </div>

              <p style={{color:"#94A3B8",fontSize:"14px",lineHeight:1.7,marginTop:"16px",maxWidth:"380px"}}>
                Zoiko AI Logistics unifies validation, audit, reconciliation, and execution with the power of AI to deliver transparency, compliance, and operational excellence.
              </p>

              {/* Features */}
              <div style={{marginTop:"20px",display:"flex",flexDirection:"column",gap:"10px"}}>
                {FEATURES.map(f=>(
                  <div key={f.title} style={{display:"flex",alignItems:"center",gap:"14px",padding:"12px 16px",borderRadius:"14px",background:"rgba(255,255,255,0.03)",border:"1px solid rgba(255,255,255,0.07)",cursor:"default",transition:"transform .2s"}}
                       onMouseEnter={e=>(e.currentTarget.style.transform="translateX(4px)")}
                       onMouseLeave={e=>(e.currentTarget.style.transform="translateX(0)")}>
                    <div style={{width:"40px",height:"40px",borderRadius:"50%",display:"flex",alignItems:"center",justifyContent:"center",background:`${f.color}20`,border:`1px solid ${f.color}35`,flexShrink:0}}>
                      <f.icon size={18} color={f.color}/>
                    </div>
                    <div>
                      <p style={{color:"white",fontSize:"14px",fontWeight:700,margin:0}}>{f.title}</p>
                      <p style={{color:"#64748B",fontSize:"12px",margin:"2px 0 0"}}>{f.desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Stats bar */}
            <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:"10px",padding:"16px",borderRadius:"16px",background:"rgba(255,255,255,0.04)",border:"1px solid rgba(255,255,255,0.08)"}}>
              {STATS.map(s=>(
                <div key={s.label} style={{textAlign:"center"}}>
                  <p style={{color:s.color,fontSize:"22px",fontWeight:900,margin:0}}>{s.value}</p>
                  <p style={{color:"#475569",fontSize:"10px",margin:"2px 0 0",lineHeight:1.3}}>{s.label}</p>
                </div>
              ))}
            </div>
          </div>

          {/* RIGHT — Login card */}
          <div style={{width:"420px",flexShrink:0}}>
            <div style={{borderRadius:"24px",overflow:"hidden",background:card.bg,boxShadow:"0 32px 80px rgba(0,0,0,0.5),0 0 0 1px rgba(255,255,255,0.12)",transition:"background .3s"}}>

              {/* Top rainbow strip */}
              <div style={{height:"4px",background:"linear-gradient(90deg,#2563EB,#60A5FA,#34D399,#A78BFA,#F472B6)"}} />

              <div style={{padding:"24px 28px 0"}}>

                {/* ── LOGIN ────────────────────────────────────── */}
                {flow === "login" && <>

                  {/* Security badges */}
                  <div style={{display:"flex",alignItems:"center",justifyContent:"center",gap:"16px",padding:"10px",borderRadius:"12px",background:secBadge.bg,border:`1px solid ${secBadge.border}`,marginBottom:"16px"}}>
                    {[{icon:ShieldCheck,label:"256-bit Encrypted",c:"#2563EB"},{icon:Lock,label:"SOC 2 Certified",c:"#059669"},{icon:Zap,label:"AI-Secured",c:"#7C3AED"}].map(b=>(
                      <div key={b.label} style={{display:"flex",alignItems:"center",gap:"5px"}}>
                        <b.icon size={12} color={b.c}/>
                        <span style={{fontSize:"10px",fontWeight:600,color:"#64748B"}}>{b.label}</span>
                      </div>
                    ))}
                  </div>

                  {/* Heading */}
                  <div style={{textAlign:"center",marginBottom:"16px"}}>
                    <h2 style={{fontSize:"22px",fontWeight:900,color:card.heading,margin:0,transition:"color .3s"}}>Welcome Back</h2>
                    <p style={{color:card.sub,fontSize:"13px",margin:"4px 0 0",transition:"color .3s"}}>Sign in to your Zoiko AI Logistics account</p>
                  </div>



                  {/* Form */}
                  <form onSubmit={handleLogin}>
                    {/* Email */}
                    <div style={{marginBottom:"12px"}}>
                      <label style={{display:"block",fontSize:"11px",fontWeight:700,color:card.label,letterSpacing:"0.1em",marginBottom:"6px"}}>EMAIL</label>
                      <div style={{position:"relative"}}>
                        <div style={{position:"absolute",left:"12px",top:"50%",transform:"translateY(-50%)",width:"28px",height:"28px",borderRadius:"8px",background:email?"rgba(37,99,235,0.1)":"rgba(100,116,139,0.08)",display:"flex",alignItems:"center",justifyContent:"center"}}>
                          <Mail size={14} color={email?"#2563EB":"#94A3B8"}/>
                        </div>
                        <input type="email" value={email} onChange={e=>{setEmail(e.target.value);setError("");}}
                               placeholder="Enter your email" autoComplete="email" required
                               style={inputStyle(!!email)} />
                      </div>
                    </div>

                    {/* Password */}
                    <div style={{marginBottom:"10px"}}>
                      <label style={{display:"block",fontSize:"11px",fontWeight:700,color:card.label,letterSpacing:"0.1em",marginBottom:"6px"}}>PASSWORD</label>
                      <div style={{position:"relative"}}>
                        <div style={{position:"absolute",left:"12px",top:"50%",transform:"translateY(-50%)",width:"28px",height:"28px",borderRadius:"8px",background:password?"rgba(37,99,235,0.1)":"rgba(100,116,139,0.08)",display:"flex",alignItems:"center",justifyContent:"center"}}>
                          <Lock size={14} color={password?"#2563EB":"#94A3B8"}/>
                        </div>
                        <input type={showPw?"text":"password"} value={password} onChange={e=>{setPassword(e.target.value);setError("");}}
                               placeholder="Enter your password" autoComplete="current-password" required
                               style={{...inputStyle(!!password),paddingRight:"48px"}} />
                        <button type="button" onClick={()=>setShowPw(v=>!v)} tabIndex={-1}
                                style={{position:"absolute",right:"12px",top:"50%",transform:"translateY(-50%)",background:"none",border:"none",cursor:"pointer",color:"#94A3B8",padding:"4px",borderRadius:"6px"}}>
                          {showPw ? <EyeOff size={16}/> : <Eye size={16}/>}
                        </button>
                      </div>
                    </div>

                    {/* Remember + Forgot */}
                    <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:"12px"}}>
                      <label style={{display:"flex",alignItems:"center",gap:"8px",cursor:"pointer",fontSize:"13px",color:card.label}}>
                        <input type="checkbox" checked={remember} onChange={e=>setRemember(e.target.checked)} style={{width:"14px",height:"14px",accentColor:"#2563EB"}}/>
                        Remember me
                      </label>
                      <Link to="/forgot-password"
                            style={{color:"#2563EB",fontSize:"13px",fontWeight:700,cursor:"pointer",textDecoration:"none"}}>
                        Forgot password?
                      </Link>
                    </div>

                    {error && (
                      <div style={{borderRadius:"10px",padding:"10px 14px",background:"#FEF2F2",color:"#DC2626",fontSize:"12px",fontWeight:500,border:"1px solid #FECACA",marginBottom:"10px"}}>{error}</div>
                    )}

                    {/* Sign In */}
                    <button type="submit" disabled={loading||!email||!password}
                            style={{width:"100%",borderRadius:"12px",padding:"14px",fontSize:"14px",fontWeight:700,color:"white",border:"none",cursor:loading||!email||!password?"not-allowed":"pointer",background:loading||!email||!password?"#93C5FD":"linear-gradient(135deg,#1D4ED8 0%,#2563EB 60%,#3B82F6 100%)",boxShadow:loading||!email||!password?"none":"0 8px 24px rgba(37,99,235,0.4)",transition:"all .2s",display:"flex",alignItems:"center",justifyContent:"center",gap:"8px",marginBottom:"12px"}}>
                      {loading
                        ? <><div style={{width:"16px",height:"16px",borderRadius:"50%",border:"2px solid rgba(255,255,255,0.4)",borderTop:"2px solid white",animation:"spin 0.7s linear infinite"}}/> Signing in…</>
                        : <><Lock size={15}/> Sign In</>
                      }
                    </button>
                  </form>

                  {/* Divider */}
                  <div style={{display:"flex",alignItems:"center",gap:"12px",marginBottom:"10px"}}>
                    <div style={{flex:1,height:"1px",background:"linear-gradient(to right,transparent,#E2E8F0)"}}/>
                    <span style={{fontSize:"11px",fontWeight:600,color:"#CBD5E1",whiteSpace:"nowrap"}}>or continue with</span>
                    <div style={{flex:1,height:"1px",background:"linear-gradient(to left,transparent,#E2E8F0)"}}/>
                  </div>

                  {/* Google — proper size */}
                  <button type="button" onClick={handleGoogle}
                          style={{width:"100%",display:"flex",alignItems:"center",justifyContent:"center",gap:"10px",borderRadius:"12px",padding:"12px",fontSize:"14px",fontWeight:600,color:"#334155",background:"white",border:"1.5px solid #E2E8F0",cursor:"pointer",boxShadow:"0 2px 8px rgba(0,0,0,0.05)",transition:"all .2s",marginBottom:"12px"}}>
                    <GoogleIcon/>
                    Sign in with Google
                  </button>

                  <div style={{display:"flex",alignItems:"center",justifyContent:"center",gap:"8px",paddingBottom:"4px"}}>
                    <span style={{fontSize:"12px",color:"#94A3B8"}}>Don't have an account?</span>
                    <button type="button" onClick={()=>{setFlow("register");setError("");}}
                            style={{display:"flex",alignItems:"center",gap:"5px",background:"none",border:"1.5px solid #2563EB",borderRadius:"8px",padding:"5px 12px",color:"#2563EB",fontSize:"12px",fontWeight:700,cursor:"pointer",transition:"all .2s"}}
                            onMouseEnter={e=>(e.currentTarget.style.background="#EFF6FF")}
                            onMouseLeave={e=>(e.currentTarget.style.background="none")}>
                      <UserPlus size={12}/> Register
                    </button>
                  </div>
                </>}

                {/* ── REGISTER — Organization Signup ────────────── */}
                {flow === "register" && (
                  <div style={{paddingBottom:"8px"}}>
                    <button onClick={()=>{setFlow("login");setError("");}} style={{display:"flex",alignItems:"center",gap:"6px",background:"none",border:"none",color:"#94A3B8",fontSize:"13px",cursor:"pointer",marginBottom:"12px",padding:0}}>
                      <ArrowLeft size={14}/> Back to sign in
                    </button>
                    <h2 style={{fontSize:"20px",fontWeight:900,color:card.heading,margin:"0 0 4px"}}>Create Your Organization</h2>
                    <p style={{color:card.sub,fontSize:"12px",marginBottom:"16px"}}>Set up your workspace. You'll be the admin.</p>
                    <form onSubmit={handleRegister} style={{display:"flex",flexDirection:"column",gap:"10px"}}>
                      {[
                        {icon:Building2, key:"org",  label:"Organization Name", ph:"Amazon India",         type:"text"  },
                        {icon:Users,     key:"name", label:"Admin Full Name",   ph:"Ravi Kumar",           type:"text"  },
                        {icon:Mail,      key:"email",label:"Admin Work Email",  ph:"ravi@amazon.in",       type:"email" },
                        {icon:Lock,      key:"password",label:"Password",       ph:"At least 8 characters", type:"password" },
                      ].map(f=>(
                        <div key={f.key}>
                          <label style={{fontSize:"10px",fontWeight:700,color:card.label,letterSpacing:"0.1em",display:"block",marginBottom:"5px"}}>{f.label.toUpperCase()}</label>
                          <div style={{position:"relative"}}>
                            <div style={{position:"absolute",left:"12px",top:"50%",transform:"translateY(-50%)",width:"24px",height:"24px",borderRadius:"6px",background:"rgba(100,116,139,0.08)",display:"flex",alignItems:"center",justifyContent:"center"}}>
                              <f.icon size={12} color="#94A3B8"/>
                            </div>
                            <input type={f.type} required placeholder={f.ph}
                                   value={(reg as Record<string,string>)[f.key]}
                                   onChange={e=>setReg(r=>({...r,[f.key]:e.target.value}))}
                                   style={{...inputStyle(false),paddingLeft:"44px",fontSize:"13px"}}/>
                          </div>
                        </div>
                      ))}
                      {error && <div style={{borderRadius:"10px",padding:"8px 12px",background:"#FEF2F2",color:"#DC2626",fontSize:"12px",border:"1px solid #FECACA"}}>{error}</div>}
                      <button type="submit" disabled={loading}
                              style={{width:"100%",borderRadius:"12px",padding:"13px",fontSize:"14px",fontWeight:700,color:"white",border:"none",cursor:loading?"not-allowed":"pointer",background:loading?"#93C5FD":"linear-gradient(135deg,#1D4ED8,#3B82F6)",boxShadow:"0 8px 24px rgba(37,99,235,0.35)",display:"flex",alignItems:"center",justifyContent:"center",gap:"8px"}}>
                        {loading ? "Creating account…" : <><UserPlus size={15}/> Create Account</>}
                      </button>
                    </form>
                  </div>
                )}

                {/* ── RECOVERY ────────────────────────────────── */}
                {flow === "recovery" && (
                  <div style={{paddingBottom:"8px"}}>
                    <button onClick={()=>{setFlow("login");setError("");}} style={{display:"flex",alignItems:"center",gap:"6px",background:"none",border:"none",color:"#94A3B8",fontSize:"13px",cursor:"pointer",marginBottom:"16px",padding:0}}>
                      <ArrowLeft size={14}/> Back to sign in
                    </button>
                    <h2 style={{fontSize:"22px",fontWeight:900,color:"#0F172A",margin:"0 0 4px"}}>Reset Password</h2>
                    <p style={{color:"#94A3B8",fontSize:"13px",marginBottom:"20px"}}>Enter your email to receive recovery instructions.</p>
                    <form onSubmit={handleRecovery}>
                      <div style={{position:"relative",marginBottom:"14px"}}>
                        <div style={{position:"absolute",left:"12px",top:"50%",transform:"translateY(-50%)",width:"28px",height:"28px",borderRadius:"8px",background:"rgba(100,116,139,0.08)",display:"flex",alignItems:"center",justifyContent:"center"}}>
                          <Mail size={14} color="#94A3B8"/>
                        </div>
                        <input type="email" value={recEmail} onChange={e=>setRecEmail(e.target.value)} placeholder="Enter your email" required style={inputStyle(!!recEmail)}/>
                      </div>
                      <button type="submit" disabled={loading||!recEmail}
                              style={{width:"100%",borderRadius:"12px",padding:"14px",fontSize:"14px",fontWeight:700,color:"white",border:"none",cursor:loading||!recEmail?"not-allowed":"pointer",background:loading||!recEmail?"#93C5FD":"linear-gradient(135deg,#1D4ED8,#3B82F6)",boxShadow:"0 8px 24px rgba(37,99,235,0.35)",marginBottom:"8px"}}>
                        {loading ? "Sending…" : "Send Instructions"}
                      </button>
                    </form>
                  </div>
                )}

                {flow === "recovery-sent" && (
                  <div style={{textAlign:"center",padding:"16px 0 24px"}}>
                    <div style={{width:"60px",height:"60px",borderRadius:"50%",background:"linear-gradient(135deg,#ECFDF5,#D1FAE5)",border:"2px solid #6EE7B7",display:"flex",alignItems:"center",justifyContent:"center",margin:"0 auto 16px"}}>
                      <CheckCircle2 size={28} color="#10B981"/>
                    </div>
                    <h2 style={{fontSize:"22px",fontWeight:900,color:"#0F172A",margin:"0 0 6px"}}>Check your inbox</h2>
                    <p style={{color:"#94A3B8",fontSize:"13px",marginBottom:"16px"}}>Recovery instructions sent if an account exists.</p>
                    <button onClick={()=>{setFlow("login");setError("");}} style={{background:"none",border:"none",color:"#2563EB",fontSize:"13px",fontWeight:700,cursor:"pointer"}}>
                      Return to sign in
                    </button>
                  </div>
                )}

              </div>

              {/* Card footer */}
              <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",padding:"10px 28px",background:card.foot,borderTop:`1px solid ${card.footBorder}`,transition:"background .3s"}}>
                <div style={{display:"flex",alignItems:"center",gap:"5px"}}>
                  <ShieldCheck size={11} color="#10B981"/>
                  <span style={{fontSize:"10px",fontWeight:600,color:"#94A3B8"}}>SSL Secured</span>
                </div>
                <div style={{display:"flex",gap:"14px"}}>
                  {["Privacy","Terms","Security"].map(l=>(
                    <a key={l} href="#" style={{fontSize:"10px",color:"#94A3B8",textDecoration:"none",fontWeight:500}}>{l}</a>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div style={{flexShrink:0,display:"flex",alignItems:"center",justifyContent:"center",gap:"20px",padding:"8px",color:"#334155",fontSize:"11px"}}>
          <span>© 2026 Zoiko AI Logistics. All rights reserved.</span>
          <span style={{color:"#1E293B"}}>|</span>
          <a href="#" style={{color:"#475569",textDecoration:"none"}}>Privacy Policy</a>
          <span style={{color:"#1E293B"}}>|</span>
          <a href="#" style={{color:"#475569",textDecoration:"none"}}>Terms of Service</a>
        </div>
      </div>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.5} }
        button:hover { opacity: 0.92; }
      `}</style>
    </div>
  );
}
