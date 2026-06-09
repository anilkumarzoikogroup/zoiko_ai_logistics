import { useState, useEffect, useRef } from "react";
import { useNavigate, Link } from "react-router-dom";
import {
  Mail, Lock, Shield, FileText, BarChart2, Rocket,
  ArrowLeft, CheckCircle2, Moon, Sun, ShieldCheck, Zap, Globe,
} from "lucide-react";
import axios from "axios";

const API = import.meta.env.VITE_API_BASE || "/api";

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

type Step = "email" | "otp" | "password" | "done";

export default function ForgotPassword() {
  const nav = useNavigate();
  const [step, setStep] = useState<Step>("email");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [email, setEmail] = useState("");
  const [otp, setOtp] = useState("");
  const [verifyToken, setVerifyToken] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [token, setToken] = useState("");
  const [dark, setDark] = useState(true);
  const [time, setTime] = useState(new Date());

  const [timer, setTimer] = useState(600);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    if (step === "otp" && timer > 0) {
      timerRef.current = setInterval(() => setTimer(t => t - 1), 1000);
      return () => { if (timerRef.current) clearInterval(timerRef.current); };
    }
    if (timer <= 0 && timerRef.current) {
      clearInterval(timerRef.current);
    }
  }, [step, timer]);

  function formatTime(sec: number) {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m}:${s.toString().padStart(2, "0")}`;
  }

  async function handleSendOtp(e: React.FormEvent) {
    e.preventDefault(); setLoading(true); setError("");
    try {
      await axios.post(`${API}/v1/auth/forgot-password`, { email });
      setStep("otp");
      setTimer(600);
    } catch (err: unknown) {
      const msg = axios.isAxiosError(err) ? err.response?.data?.detail : null;
      setError(typeof msg === "string" ? msg : "Failed to send OTP");
    } finally { setLoading(false); }
  }

  async function handleVerifyOtp(e: React.FormEvent) {
    e.preventDefault(); setLoading(true); setError("");
    try {
      const { data } = await axios.post(`${API}/v1/auth/verify-otp`, { email, otp });
      setVerifyToken(data.verify_token);
      setStep("password");
    } catch (err: unknown) {
      const msg = axios.isAxiosError(err) ? err.response?.data?.detail : null;
      setError(typeof msg === "string" ? msg : "Invalid OTP");
    } finally { setLoading(false); }
  }

  async function handleResetPassword(e: React.FormEvent) {
    e.preventDefault(); setLoading(true); setError("");
    if (password !== confirmPassword) {
      setError("Passwords do not match"); setLoading(false); return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters"); setLoading(false); return;
    }
    try {
      const { data } = await axios.post(`${API}/v1/auth/reset-password`, {
        email, verify_token: verifyToken, password, confirm_password: confirmPassword,
      });
      setToken(data.token);
      setStep("done");
    } catch (err: unknown) {
      const msg = axios.isAxiosError(err) ? err.response?.data?.detail : null;
      setError(typeof msg === "string" ? msg : "Password reset failed");
    } finally { setLoading(false); }
  }

  function goToLogin() {
    if (token) localStorage.setItem("zoiko_jwt", token);
    nav("/login");
  }

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
      <div style={{position:"absolute",top:"-10%",left:"-5%",width:"500px",height:"500px",borderRadius:"50%",filter:"blur(100px)",background:"radial-gradient(circle,rgba(29,78,216,.4) 0%,transparent 70%)",zIndex:0,pointerEvents:"none",animation:"pulse 4s ease-in-out infinite"}} />
      <div style={{position:"absolute",bottom:"-10%",left:"20%",width:"400px",height:"400px",borderRadius:"50%",filter:"blur(80px)",background:"radial-gradient(circle,rgba(14,165,233,.3) 0%,transparent 70%)",zIndex:0,pointerEvents:"none",animation:"pulse 6s ease-in-out infinite"}} />
      <div style={{position:"absolute",inset:0,zIndex:0,opacity:0.08,backgroundImage:"radial-gradient(circle,rgba(255,255,255,.5) 1px,transparent 1px)",backgroundSize:"28px 28px",pointerEvents:"none"}} />

      {/* ── All content ────────────────────────────────────────────── */}
      <div style={{position:"relative",zIndex:10,display:"flex",flexDirection:"column",height:"100%"}}>

        {/* Top bar */}
        <div style={{flexShrink:0,display:"flex",alignItems:"center",justifyContent:"space-between",padding:"14px 40px"}}>
          <div style={{display:"flex",alignItems:"center",gap:"12px"}}>
            <img src="/logo-dark.jpg" alt="ZoikoAI"
                 style={{height:"64px",width:"auto",objectFit:"contain",filter:"drop-shadow(0 4px 12px rgba(96,165,250,0.3))"}}
                 onError={e => {
                   e.currentTarget.style.display = "none";
                   const fb = e.currentTarget.nextElementSibling as HTMLElement | null;
                   if (fb) fb.style.display = "flex";
                 }} />
            <div style={{display:"flex",flexDirection:"column"}}>
              <div style={{display:"flex",alignItems:"baseline",gap:"2px"}}>
                <span style={{color:"white",fontSize:"28px",fontWeight:900,lineHeight:1,letterSpacing:"-0.5px"}}>Zoiko</span>
                <span style={{fontSize:"28px",fontWeight:900,lineHeight:1,background:"linear-gradient(90deg,#60A5FA,#34D399)",WebkitBackgroundClip:"text",WebkitTextFillColor:"transparent"}}>AI</span>
                <sup style={{color:"white",fontSize:"10px",marginBottom:"4px"}}>™</sup>
              </div>
              <span style={{fontSize:"10px",fontWeight:700,letterSpacing:"0.2em",color:"#60A5FA"}}>AI LOGISTICS</span>
            </div>
          </div>
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

          {/* LEFT — same as Login */}
          <div style={{flex:"1 1 0",minWidth:"360px",maxWidth:"520px",display:"flex",flexDirection:"column",height:"100%",justifyContent:"space-between",paddingBottom:"8px"}}>
            <div>
              <div style={{display:"inline-flex",alignItems:"center",gap:"8px",padding:"6px 14px",borderRadius:"20px",background:"rgba(96,165,250,0.1)",border:"1px solid rgba(96,165,250,0.25)",marginBottom:"20px"}}>
                <Zap size={12} color="#60A5FA"/>
                <span style={{color:"#60A5FA",fontSize:"11px",fontWeight:700,letterSpacing:"0.15em"}}>GOVERNED AUTONOMOUS</span>
              </div>
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
            <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:"10px",padding:"16px",borderRadius:"16px",background:"rgba(255,255,255,0.04)",border:"1px solid rgba(255,255,255,0.08)"}}>
              {STATS.map(s=>(
                <div key={s.label} style={{textAlign:"center"}}>
                  <p style={{color:s.color,fontSize:"22px",fontWeight:900,margin:0}}>{s.value}</p>
                  <p style={{color:"#475569",fontSize:"10px",margin:"2px 0 0",lineHeight:1.3}}>{s.label}</p>
                </div>
              ))}
            </div>
          </div>

          {/* RIGHT — Password reset card */}
          <div style={{width:"420px",flexShrink:0}}>
            <div style={{borderRadius:"24px",overflow:"hidden",background:card.bg,boxShadow:"0 32px 80px rgba(0,0,0,0.5),0 0 0 1px rgba(255,255,255,0.12)",transition:"background .3s"}}>
              <div style={{height:"4px",background:"linear-gradient(90deg,#2563EB,#60A5FA,#34D399,#A78BFA,#F472B6)"}} />
              <div style={{padding:"24px 28px 0"}}>

                {/* Security badges */}
                <div style={{display:"flex",alignItems:"center",justifyContent:"center",gap:"16px",padding:"10px",borderRadius:"12px",background:secBadge.bg,border:`1px solid ${secBadge.border}`,marginBottom:"12px"}}>
                  {[{icon:ShieldCheck,label:"256-bit Encrypted",c:"#2563EB"},{icon:Lock,label:"SOC 2 Certified",c:"#059669"},{icon:Zap,label:"AI-Secured",c:"#7C3AED"}].map(b=>(
                    <div key={b.label} style={{display:"flex",alignItems:"center",gap:"5px"}}>
                      <b.icon size={12} color={b.c}/>
                      <span style={{fontSize:"10px",fontWeight:600,color:"#64748B"}}>{b.label}</span>
                    </div>
                  ))}
                </div>

                {error && (
                  <div style={{borderRadius:"10px",padding:"10px 14px",background:"#FEF2F2",color:"#DC2626",fontSize:"12px",fontWeight:500,border:"1px solid #FECACA",marginBottom:"12px"}}>{error}</div>
                )}

                {/* Step 1: Email */}
                {step === "email" && (
                  <div style={{paddingBottom:"8px"}}>
                    <div style={{textAlign:"center",marginBottom:"16px"}}>
                      <h2 style={{fontSize:"22px",fontWeight:900,color:card.heading,margin:0,transition:"color .3s"}}>Forgot Password</h2>
                      <p style={{color:card.sub,fontSize:"13px",margin:"4px 0 0",transition:"color .3s"}}>Enter your email to receive a 6-digit OTP.</p>
                    </div>
                    <form onSubmit={handleSendOtp}>
                      <div style={{marginBottom:"14px"}}>
                        <label style={{display:"block",fontSize:"11px",fontWeight:700,color:card.label,letterSpacing:"0.1em",marginBottom:"6px"}}>EMAIL</label>
                        <div style={{position:"relative"}}>
                          <div style={{position:"absolute",left:"12px",top:"50%",transform:"translateY(-50%)",width:"28px",height:"28px",borderRadius:"8px",background:email?"rgba(37,99,235,0.1)":"rgba(100,116,139,0.08)",display:"flex",alignItems:"center",justifyContent:"center"}}>
                            <Mail size={14} color={email?"#2563EB":"#94A3B8"}/>
                          </div>
                          <input type="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="Enter your email" required style={inputStyle(!!email)} />
                        </div>
                      </div>
                      <button type="submit" disabled={loading||!email}
                              style={{width:"100%",borderRadius:"12px",padding:"14px",fontSize:"14px",fontWeight:700,color:"white",border:"none",cursor:loading||!email?"not-allowed":"pointer",background:loading||!email?"#93C5FD":"linear-gradient(135deg,#1D4ED8 0%,#2563EB 60%,#3B82F6 100%)",boxShadow:loading||!email?"none":"0 8px 24px rgba(37,99,235,0.4)",transition:"all .2s",display:"flex",alignItems:"center",justifyContent:"center",gap:"8px",marginBottom:"12px"}}>
                        {loading
                          ? <><div style={{width:"16px",height:"16px",borderRadius:"50%",border:"2px solid rgba(255,255,255,0.4)",borderTop:"2px solid white",animation:"spin 0.7s linear infinite"}}/> Sending OTP…</>
                          : <><Mail size={15}/> Send OTP</>
                        }
                      </button>
                    </form>
                  </div>
                )}

                {/* Step 2: OTP */}
                {step === "otp" && (
                  <div style={{paddingBottom:"8px"}}>
                    <div style={{textAlign:"center",marginBottom:"16px"}}>
                      <h2 style={{fontSize:"22px",fontWeight:900,color:card.heading,margin:0,transition:"color .3s"}}>Enter OTP</h2>
                      <p style={{color:card.sub,fontSize:"13px",margin:"4px 0 0",transition:"color .3s"}}>Code sent to <strong style={{color:card.heading}}>{email}</strong></p>
                    </div>
                    <p style={{color:timer <= 60 ? "#DC2626" : "#64748B",fontSize:"28px",fontWeight:900,textAlign:"center",margin:"0 0 16px",fontFamily:"monospace"}}>
                      {formatTime(timer)}
                    </p>
                    <form onSubmit={handleVerifyOtp}>
                      <div style={{marginBottom:"14px"}}>
                        <label style={{display:"block",fontSize:"11px",fontWeight:700,color:card.label,letterSpacing:"0.1em",marginBottom:"6px",textAlign:"center"}}>6-DIGIT OTP</label>
                        <input type="text" inputMode="numeric" maxLength={6} value={otp} onChange={e=>setOtp(e.target.value.replace(/\D/g,"").slice(0,6))}
                               placeholder="000000" required
                               style={{...inputStyle(!!otp),padding:"14px",textAlign:"center",fontSize:"24px",letterSpacing:"12px",fontWeight:900}} />
                      </div>
                      <button type="submit" disabled={loading||otp.length!==6||timer<=0}
                              style={{width:"100%",borderRadius:"12px",padding:"14px",fontSize:"14px",fontWeight:700,color:"white",border:"none",cursor:loading||otp.length!==6||timer<=0?"not-allowed":"pointer",background:loading||otp.length!==6||timer<=0?"#93C5FD":"linear-gradient(135deg,#1D4ED8 0%,#2563EB 60%,#3B82F6 100%)",boxShadow:loading||otp.length!==6||timer<=0?"none":"0 8px 24px rgba(37,99,235,0.4)",display:"flex",alignItems:"center",justifyContent:"center",gap:"8px",marginBottom:"10px"}}>
                        {loading ? "Verifying…" : "Verify OTP"}
                      </button>
                      <button type="button" onClick={()=>{setStep("email");setOtp("");setError("");}}
                              style={{width:"100%",padding:"8px",background:"none",border:"none",color:"#2563EB",fontSize:"12px",fontWeight:600,cursor:"pointer"}}>
                        Change email
                      </button>
                    </form>
                  </div>
                )}

                {/* Step 3: New Password */}
                {step === "password" && (
                  <div style={{paddingBottom:"8px"}}>
                    <div style={{textAlign:"center",marginBottom:"16px"}}>
                      <h2 style={{fontSize:"22px",fontWeight:900,color:card.heading,margin:0,transition:"color .3s"}}>New Password</h2>
                      <p style={{color:card.sub,fontSize:"13px",margin:"4px 0 0",transition:"color .3s"}}>Choose a strong password for your account.</p>
                    </div>
                    <form onSubmit={handleResetPassword}>
                      <div style={{marginBottom:"12px"}}>
                        <label style={{display:"block",fontSize:"11px",fontWeight:700,color:card.label,letterSpacing:"0.1em",marginBottom:"6px"}}>NEW PASSWORD</label>
                        <div style={{position:"relative"}}>
                          <div style={{position:"absolute",left:"12px",top:"50%",transform:"translateY(-50%)",width:"28px",height:"28px",borderRadius:"8px",background:password?"rgba(37,99,235,0.1)":"rgba(100,116,139,0.08)",display:"flex",alignItems:"center",justifyContent:"center"}}>
                            <Lock size={14} color={password?"#2563EB":"#94A3B8"}/>
                          </div>
                          <input type="password" value={password} onChange={e=>setPassword(e.target.value)} placeholder="At least 8 characters" required minLength={8} style={inputStyle(!!password)} />
                        </div>
                      </div>
                      <div style={{marginBottom:"14px"}}>
                        <label style={{display:"block",fontSize:"11px",fontWeight:700,color:card.label,letterSpacing:"0.1em",marginBottom:"6px"}}>CONFIRM PASSWORD</label>
                        <div style={{position:"relative"}}>
                          <div style={{position:"absolute",left:"12px",top:"50%",transform:"translateY(-50%)",width:"28px",height:"28px",borderRadius:"8px",background:confirmPassword?"rgba(37,99,235,0.1)":"rgba(100,116,139,0.08)",display:"flex",alignItems:"center",justifyContent:"center"}}>
                            <Lock size={14} color={confirmPassword?"#2563EB":"#94A3B8"}/>
                          </div>
                          <input type="password" value={confirmPassword} onChange={e=>setConfirmPassword(e.target.value)} placeholder="Re-enter password" required minLength={8} style={inputStyle(!!confirmPassword)} />
                        </div>
                      </div>
                      <button type="submit" disabled={loading||!password||!confirmPassword}
                              style={{width:"100%",borderRadius:"12px",padding:"14px",fontSize:"14px",fontWeight:700,color:"white",border:"none",cursor:loading||!password||!confirmPassword?"not-allowed":"pointer",background:loading||!password||!confirmPassword?"#93C5FD":"linear-gradient(135deg,#1D4ED8 0%,#2563EB 60%,#3B82F6 100%)",boxShadow:loading||!password||!confirmPassword?"none":"0 8px 24px rgba(37,99,235,0.4)",display:"flex",alignItems:"center",justifyContent:"center",gap:"8px",marginBottom:"12px"}}>
                        {loading ? "Resetting…" : <><Lock size={15}/> Reset Password</>}
                      </button>
                    </form>
                  </div>
                )}

                {/* Step 4: Done */}
                {step === "done" && (
                  <div style={{textAlign:"center",padding:"8px 0 24px"}}>
                    <div style={{width:"60px",height:"60px",borderRadius:"50%",background:"linear-gradient(135deg,#ECFDF5,#D1FAE7)",border:"2px solid #6EE7B7",display:"flex",alignItems:"center",justifyContent:"center",margin:"0 auto 16px"}}>
                      <CheckCircle2 size={28} color="#10B981"/>
                    </div>
                    <h2 style={{fontSize:"22px",fontWeight:900,color:card.heading,margin:"0 0 6px",transition:"color .3s"}}>Password Reset</h2>
                    <p style={{color:card.sub,fontSize:"13px",marginBottom:"20px",transition:"color .3s"}}>Your password has been reset. You are now logged in.</p>
                    <Link to="/"
                      style={{display:"block",width:"100%",borderRadius:"12px",padding:"14px",fontSize:"14px",fontWeight:700,color:"white",textDecoration:"none",textAlign:"center",background:"linear-gradient(135deg,#059669,#10B981)",boxShadow:"0 8px 24px rgba(16,185,129,0.35)"}}>
                      Go to Dashboard
                    </Link>
                  </div>
                )}

                {/* Back link (not on done) */}
                {step !== "done" && (
                  <Link to="/login" style={{display:"flex",alignItems:"center",justifyContent:"center",gap:"6px",color:"#94A3B8",fontSize:"12px",fontWeight:600,textDecoration:"none",padding:"4px 0 12px"}}>
                    <ArrowLeft size={14}/> Back to sign in
                  </Link>
                )}

              </div>
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
