import { useEffect, useState } from "react";
import { sendJson } from "../../lib/api/client";
import { Async, useLoad } from "../../lib/hooks";

export default function Settings() {
  const me = useLoad<any>("/me");
  const mem = useLoad<any[]>("/memory");
  const [s, setS] = useState<any>(null);
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => { if (me.data) setS(me.data.settings); }, [me.data]);

  async function save() {
    try { await sendJson("PUT", "/me/settings", { hourly_rate: s.hourly_rate, floor: s.floor, weekly_connects_budget: +s.weekly_connects_budget, autonomy: s.autonomy, saved_searches: s.saved_searches, marketplace: s.marketplace }); setMsg("Saved."); }
    catch (e: any) { setMsg(String(e.message)); }
  }
  async function connectUpwork() {
    try { const r = await sendJson("GET", "/connect/upwork/start"); window.location.href = r.authorize_url; }
    catch (e: any) { setMsg(String(e.message)); }
  }
  return (
    <>
      <h1>Settings</h1>
      <Async s={me}>
        {() => s && (
          <div className="grid">
            <div className="card">
              <h2>Limits and autonomy</h2>
              <label htmlFor="wb">Weekly Connects budget</label><input id="wb" type="number" min={0} value={s.weekly_connects_budget} onChange={(e) => setS({ ...s, weekly_connects_budget: e.target.value })} data-testid="weekly-budget" />
              <label htmlFor="auto">Autonomy</label>
              <select id="auto" value={s.autonomy} onChange={(e) => setS({ ...s, autonomy: e.target.value })}>
                <option value="suggest">Suggest only (you decide every job)</option><option value="auto_skip_low_fit">Auto-skip clearly low-fit jobs</option></select>
              <p className="muted small">GigBid never sends a proposal or message on its own. There is no auto-send setting.</p>
              <h2>Saved searches</h2>
              {s.saved_searches.map((q: any, i: number) => (
                <div className="row" key={i}>
                  <input aria-label="keywords" value={q.query} onChange={(e) => { const x = [...s.saved_searches]; x[i] = { ...q, query: e.target.value }; setS({ ...s, saved_searches: x }); }} />
                  <input aria-label="interval minutes" type="number" min={60} style={{ width: 110 }} value={q.interval_minutes} onChange={(e) => { const x = [...s.saved_searches]; x[i] = { ...q, interval_minutes: +e.target.value }; setS({ ...s, saved_searches: x }); }} />
                </div>))}
              <p className="muted small">Interval in minutes (min 60). Live mode uses a conservative schedule and never scrapes.</p>
              <div className="row"><button className="primary" onClick={save} data-testid="save-settings">Save</button>{msg && <span role="status">{msg}</span>}</div>
            </div>
            <div className="card">
              <h2>Connected accounts</h2>
              <p><span className="badge ok">GigSim</span> {me.data.settings.marketplace === "gigsim" && "active"}</p>
              <button onClick={connectUpwork}>Connect Upwork (OAuth)</button>
              <p className="muted small">Live mode uses the official Upwork MCP server. Tokens are encrypted at rest.</p>
            </div>
            <div className="card">
              <h2>What GigBid has learned</h2>
              <p className="muted small">Style rules appear only after the same edit is seen on 2 different jobs. You can delete anything.</p>
              <Async s={mem} empty={(d) => d.length === 0}>
                {(items) => <ul data-testid="memory-list">{items.map((m) => (
                  <li key={m.namespace + m.key}><span className="badge">{m.namespace.split("/")[0]}</span> {m.value.rule ?? m.value.pattern ?? JSON.stringify(m.value)} {m.value.why && <span className="muted small">({m.value.why})</span>}{" "}
                    <button className="danger" aria-label={`Delete ${m.key}`} onClick={async () => { await sendJson("DELETE", `/memory/${m.namespace}/${m.key}`); mem.reload(); }}>Delete</button></li>))}</ul>}
              </Async>
            </div>
          </div>)}
      </Async>
    </>
  );
}
