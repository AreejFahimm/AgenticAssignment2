import { useState } from "react";
import { api, sendJson, setToken } from "../../lib/api/client";

const PERSONAS = [
  ["ai_ml_engineer", "AI/ML engineer"], ["fullstack_web_dev", "Full-stack web developer"], ["data_analyst", "Data analyst"],
] as const;

export default function SignIn({ onAuthed }: { onAuthed: () => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [step, setStep] = useState<"auth" | "onboard">("auth");
  const [email, setEmail] = useState(""); const [password, setPassword] = useState("");
  const [persona, setPersona] = useState<(typeof PERSONAS)[number][0]>("ai_ml_engineer");
  const [rate, setRate] = useState("30"); const [floor, setFloor] = useState("150"); const [budget, setBudget] = useState("60");
  const [query, setQuery] = useState(""); const [err, setErr] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  const [file, setFile] = useState<File | null>(null); const [msg, setMsg] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setErr(null);
    try {
      const body = mode === "register" ? { email, password, persona } : { email, password };
      const r = mode === "register" ? await api.POST("/auth/register", { body: body as any }) : await api.POST("/auth/login", { body: body as any });
      if (r.error || !r.data) throw new Error(JSON.stringify((r.error as any)?.detail ?? "sign-in failed"));
      setToken(r.data.token);
      if (mode === "register") setStep("onboard"); else { window.dispatchEvent(new Event("gigbid-auth")); onAuthed(); }
    } catch (e: any) { setErr(String(e.message ?? e)); } finally { setBusy(false); }
  }
  async function finish(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setErr(null);
    try {
      await sendJson("POST", "/connect/gigsim");
      await sendJson("PUT", "/me/settings", { hourly_rate: +rate, floor: +floor, weekly_connects_budget: +budget, autonomy: "suggest", persona,
        saved_searches: [{ name: "My search", query, interval_minutes: 240 }], marketplace: "gigsim" });
      if (file) { const fd = new FormData(); fd.append("file", file); const r = await fetch((import.meta.env.VITE_API_URL ?? "") + "/me/portfolio", { method: "POST", body: fd, headers: { Authorization: `Bearer ${localStorage.getItem("gigbid_token")}` } }); if (!r.ok) throw new Error(await r.text()); setMsg("Portfolio indexed."); }
      window.dispatchEvent(new Event("gigbid-auth")); onAuthed();
    } catch (e: any) { setErr(String(e.message ?? e)); } finally { setBusy(false); }
  }

  if (step === "onboard") {
    return (
      <form className="card" onSubmit={finish} aria-labelledby="onb-h" style={{ maxWidth: 560, margin: "0 auto" }}>
        <h1 id="onb-h">Set up your profile</h1>
        <p className="muted">Connect a marketplace, add your portfolio, and set your limits. GigBid never sends anything without your approval.</p>
        <label>Marketplace</label>
        <div className="row"><span className="badge ok">GigSim (simulator) connected</span><span className="muted small">Live Upwork is available in Settings (needs OAuth credentials).</span></div>
        <label htmlFor="rate">Hourly rate (USD)</label><input id="rate" type="number" min={1} value={rate} onChange={(e) => setRate(e.target.value)} />
        <label htmlFor="floor">Minimum fixed-price project (USD)</label><input id="floor" type="number" min={0} value={floor} onChange={(e) => setFloor(e.target.value)} />
        <label htmlFor="budget">Weekly Connects budget</label><input id="budget" data-testid="budget" type="number" min={0} value={budget} onChange={(e) => setBudget(e.target.value)} />
        <label htmlFor="query">Saved search keywords</label><input id="query" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="e.g. react, dashboard" />
        <label htmlFor="file">Upload a case study (.md, .txt or .pdf)</label><input id="file" type="file" accept=".md,.txt,.pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        {msg && <p role="status">{msg}</p>}{err && <p className="error" role="alert">{err}</p>}
        <div className="row" style={{ marginTop: 12 }}><button className="primary" disabled={busy} data-testid="finish-onboarding">Finish setup</button></div>
      </form>
    );
  }
  return (
    <form className="card" onSubmit={submit} aria-labelledby="auth-h" style={{ maxWidth: 420, margin: "0 auto" }}>
      <h1 id="auth-h">{mode === "login" ? "Sign in" : "Create your account"}</h1>
      <label htmlFor="email">Email</label><input id="email" type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
      <label htmlFor="pw">Password</label><input id="pw" type="password" required minLength={8} autoComplete={mode === "login" ? "current-password" : "new-password"} value={password} onChange={(e) => setPassword(e.target.value)} />
      {mode === "register" && (<><label htmlFor="persona">I am a</label>
        <select id="persona" value={persona} onChange={(e) => setPersona(e.target.value as any)}>{PERSONAS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></>)}
      {err && <p className="error" role="alert" data-testid="auth-error">{err}</p>}
      <div className="row" style={{ marginTop: 12 }}>
        <button className="primary" disabled={busy} data-testid="auth-submit">{mode === "login" ? "Sign in" : "Create account"}</button>
        <button type="button" onClick={() => { setMode(mode === "login" ? "register" : "login"); setErr(null); }} data-testid="auth-toggle">{mode === "login" ? "Need an account?" : "I have an account"}</button>
      </div>
    </form>
  );
}
