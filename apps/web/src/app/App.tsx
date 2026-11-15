import { NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import StatusBanner from "../components/StatusBanner";
import { getToken, sendJson, setToken } from "../lib/api/client";
import Analytics from "./analytics/page";
import Inbox from "./inbox/page";
import JobDetail from "./jobs/[id]/page";
import Messages from "./messages/page";
import Pipeline from "./pipeline/page";
import RunViewer from "./runs/[id]/page";
import Settings from "./settings/page";
import SignIn from "./signin/page";
import Studio from "./studio/[id]/page";

const LINKS: [string, string][] = [["/inbox", "Inbox"], ["/pipeline", "Pipeline"], ["/messages", "Messages"], ["/analytics", "Analytics"], ["/settings", "Settings"]];

export default function App() {
  const [authed, setAuthed] = useState(!!getToken());
  const nav = useNavigate();
  useEffect(() => { const h = () => setAuthed(!!getToken()); window.addEventListener("gigbid-auth", h); return () => window.removeEventListener("gigbid-auth", h); }, []);
  const signOut = async () => { try { await sendJson("POST", "/auth/logout"); } catch { /* ignore */ } setToken(null); setAuthed(false); nav("/signin"); };
  return (
    <>
      <a className="skip" href="#main">Skip to content</a>
      {authed && <StatusBanner />}
      <header className="top">
        <div className="inner">
          <span className="brand">GigBid</span>
          {authed && (
            <nav aria-label="Main">
              {LINKS.map(([to, label]) => <NavLink key={to} to={to}>{label}</NavLink>)}
            </nav>
          )}
          {authed && <button onClick={signOut}>Sign out</button>}
        </div>
      </header>
      <main id="main">
        <Routes>
          <Route path="/signin" element={<SignIn onAuthed={() => { setAuthed(true); nav("/inbox"); }} />} />
          <Route path="/" element={<Navigate to={authed ? "/inbox" : "/signin"} replace />} />
          {authed ? (
            <>
              <Route path="/inbox" element={<Inbox />} />
              <Route path="/jobs/:id" element={<JobDetail />} />
              <Route path="/studio/:id" element={<Studio />} />
              <Route path="/pipeline" element={<Pipeline />} />
              <Route path="/messages" element={<Messages />} />
              <Route path="/runs/:id" element={<RunViewer />} />
              <Route path="/analytics" element={<Analytics />} />
              <Route path="/settings" element={<Settings />} />
            </>
          ) : (
            <Route path="*" element={<Navigate to="/signin" replace />} />
          )}
        </Routes>
      </main>
    </>
  );
}
