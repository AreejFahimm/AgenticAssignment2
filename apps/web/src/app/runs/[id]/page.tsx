import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import RunTimeline from "../../../components/RunTimeline";
import { API_BASE, authHeaders } from "../../../lib/api/client";

export default function RunViewer() {
  const { id = "" } = useParams();
  const [trace, setTrace] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  async function loadTrace() {
    const r = await fetch(`${API_BASE}/runs/${encodeURIComponent(id)}/trace`, { headers: authHeaders() });
    if (!r.ok) { setErr("Trace is written when the run finishes or pauses."); return; }
    setTrace(await r.json()); setErr(null);
  }
  return (
    <>
      <div className="row spread"><h1>Agent run</h1><Link to={`/jobs/${encodeURIComponent(id)}`}>Job detail</Link></div>
      <div className="card"><RunTimeline threadId={id} onDone={loadTrace} /></div>
      <div className="card">
        <div className="row spread"><h2>Full trace</h2><button onClick={loadTrace} data-testid="load-trace">Open trace</button></div>
        {err && <p className="muted small">{err}</p>}
        {trace && (<>
          <p className="small muted">trace id <code data-testid="trace-id">{trace.trace_id}</code> · {trace.total_ms} ms total · {trace.tool_calls.length} tool calls</p>
          <div className="table-wrap"><table><thead><tr><th>Node</th><th>ms</th><th>Detail</th></tr></thead>
            <tbody>{trace.nodes.map((n: any, i: number) => <tr key={i}><td>{n.node}</td><td>{n.ms}</td><td className="small">{JSON.stringify(Object.fromEntries(Object.entries(n).filter(([k]) => !["node", "ms"].includes(k))))}</td></tr>)}</tbody></table></div>
          <h2>Tool calls (MCP)</h2>
          <div className="table-wrap"><table><thead><tr><th>Agent</th><th>Tool</th><th>OK</th></tr></thead>
            <tbody>{trace.tool_calls.map((c: any, i: number) => <tr key={i}><td>{c.agent}</td><td>{c.tool}</td><td>{c.ok ? "✓" : "✗ " + c.error}</td></tr>)}</tbody></table></div>
        </>)}
      </div>
    </>
  );
}
