import { useState } from "react";
import { Link } from "react-router-dom";
import { Async, useLoad } from "../../lib/hooks";
import { sendJson } from "../../lib/api/client";

const ACTION: Record<string, string> = { bid: "ok", watch: "warn", skip: "bad" };

export default function Inbox() {
  const [decision, setDecision] = useState("");
  const s = useLoad<any[]>(`/jobs${decision ? `?decision=${decision}` : ""}`, 3000);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function scan() {
    setBusy(true); setMsg(null);
    try { const r = await sendJson("POST", "/jobs/scan"); setMsg(r.marketplace_ok ? `Queued ${r.queued} jobs for analysis.` : "Marketplace unavailable: scan queued and will run when it is back."); s.reload(); }
    catch (e: any) { setMsg(String(e.message)); } finally { setBusy(false); }
  }
  return (
    <>
      <div className="row spread"><h1>Job inbox</h1>
        <div className="row">
          <label htmlFor="flt" className="small muted" style={{ margin: 0 }}>Show</label>
          <select id="flt" style={{ width: "auto" }} value={decision} onChange={(e) => setDecision(e.target.value)} data-testid="filter">
            <option value="">all</option><option value="bid">recommended: bid</option><option value="watch">watch</option><option value="skip">skip</option></select>
          <button className="primary" disabled={busy} onClick={scan} data-testid="scan">Scan for new jobs</button>
        </div></div>
      {msg && <p role="status" data-testid="scan-msg">{msg}</p>}
      <Async s={s} empty={(d) => d.length === 0}>
        {(rows) => (
          <div className="card table-wrap">
            <table data-testid="inbox-table">
              <thead><tr><th>Job</th><th>Fit</th><th>Risk</th><th>Action</th><th>Price</th><th>Connects</th><th>Status</th><th></th></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.thread_id} data-testid="inbox-row">
                    <td><Link to={`/jobs/${encodeURIComponent(r.thread_id)}`}>{r.title}</Link><div className="muted small">{r.category}</div></td>
                    <td>{r.fit != null ? <div style={{ width: 70 }}><div className="bar" aria-label={`fit ${r.fit}`}><i style={{ width: `${Math.round(r.fit * 100)}%` }} /></div><span className="small">{r.fit.toFixed(2)}</span></div> : "…"}</td>
                    <td>{r.risk != null ? <span className={`badge ${r.risk > 0.5 ? "bad" : r.risk > 0.25 ? "warn" : "ok"}`}>{r.risk.toFixed(2)}{(r.summary?.flags ?? []).length ? ` · ${r.summary.flags[0]}` : ""}</span> : "…"}</td>
                    <td>{r.decision ? <span className={`badge ${ACTION[r.decision]}`}>{r.decision}</span> : "…"}</td>
                    <td>{r.bid ? `$${r.bid}` : "–"}</td><td>{r.connects ?? "–"}</td>
                    <td><span className="badge" data-testid="row-status">{r.status}</span></td>
                    <td className="row">
                      {r.status === "waiting_approval" && <Link className="btn primary" to={`/studio/${encodeURIComponent(r.thread_id)}`}>Review</Link>}
                      {!["skipped", "submitted", "rejected"].includes(r.status) && <button onClick={async () => { await sendJson("POST", `/jobs/${encodeURIComponent(r.thread_id)}/skip`); s.reload(); }}>Skip</button>}
                      <Link to={`/runs/${encodeURIComponent(r.thread_id)}`}>Run</Link>
                    </td>
                  </tr>))}
              </tbody>
            </table>
          </div>)}
      </Async>
      {!s.loading && s.data?.length === 0 && <p className="muted">No jobs yet. Press “Scan for new jobs” to run your saved searches.</p>}
    </>
  );
}
