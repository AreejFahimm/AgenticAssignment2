import { Link, useParams } from "react-router-dom";
import { Async, useLoad } from "../../../lib/hooks";

export default function JobDetail() {
  const { id = "" } = useParams();
  const s = useLoad<any>(`/jobs/${encodeURIComponent(id)}`, 4000);
  return (
    <Async s={s}>
      {(d) => (
        <>
          <div className="row spread"><h1>{d.job?.title ?? d.run.title}</h1><span className="badge">{d.run.status}</span></div>
          <div className="row" style={{ marginBottom: 12 }}>
            {d.run.status === "waiting_approval" && <Link className="btn primary" to={`/studio/${encodeURIComponent(id)}`}>Open proposal studio</Link>}
            <Link className="btn" to={`/runs/${encodeURIComponent(id)}`}>Agent run + trace</Link>
          </div>
          {d.errors?.length > 0 && <div className="card" role="alert"><strong className="error">Needs attention</strong><ul>{d.errors.map((e: string) => <li key={e}>{e}</li>)}</ul></div>}
          <div className="two">
            <div>
              <div className="card"><h2>Bid-or-skip reasoning</h2>
                {d.decision ? <><span className={`badge ${d.decision.action === "bid" ? "ok" : d.decision.action === "watch" ? "warn" : "bad"}`}>{d.decision.action}</span>
                  <ul>{d.decision.reasons.map((r: string) => <li key={r}>{r}</li>)}</ul></> : <p className="muted">Analysis still running…</p>}
              </div>
              <div className="card table-wrap"><h2>Requirement → evidence</h2>
                {d.fit_report ? (
                  <table data-testid="evidence-matrix"><thead><tr><th>Requirement</th><th>Strength</th><th>Evidence</th></tr></thead>
                    <tbody>{d.fit_report.matrix.map((m: any) => (
                      <tr key={m.requirement}><td>{m.requirement}</td><td>{m.strength ? m.strength.toFixed(2) : <span className="badge warn">no evidence</span>}</td>
                        <td>{m.evidence_ids.length ? m.evidence_ids.join(", ") : "–"}</td></tr>))}</tbody></table>
                ) : <p className="muted">Pending…</p>}
              </div>
              <div className="card"><h2>Job spec</h2>
                {d.job_spec ? <><p><b>Skills:</b> {d.job_spec.required_skills.join(", ") || "–"}</p><p><b>Deliverables:</b></p>
                  <ul>{d.job_spec.deliverables.map((x: string) => <li key={x}>{x}</li>)}</ul>
                  <p className="muted small">Budget {d.job_spec.budget_type}: {d.job_spec.budget_min ?? "?"}–{d.job_spec.budget_max ?? "?"} USD</p></> : <p className="muted">Pending…</p>}
                <details><summary>Job post (untrusted text)</summary><p style={{ whiteSpace: "pre-wrap" }}>{d.job?.description}</p></details>
              </div>
            </div>
            <div>
              <div className="card"><h2>Risk</h2>
                {d.risk_report ? <><span className={`badge ${d.risk_report.score > 0.5 ? "bad" : d.risk_report.score > 0.25 ? "warn" : "ok"}`}>score {d.risk_report.score}</span>
                  <p className="small">{d.risk_report.explanation}</p>
                  <div className="row">{d.risk_report.flags.map((f: string) => <span key={f} className="badge bad">{f}</span>)}</div></> : <p className="muted">Pending…</p>}
              </div>
              <div className="card"><h2>Price rationale</h2>
                {d.price_quote ? <><p><b>${d.price_quote.bid_amount}</b> · {d.price_quote.connects_cost} Connects {d.price_quote.worth_connects ? "" : <span className="badge bad">not worth it</span>}</p>
                  <p className="small muted">{d.price_quote.rationale}</p>
                  {d.price_quote.band_low != null && <p className="small">Market band: ${d.price_quote.band_low}–${d.price_quote.band_high}</p>}</> : <p className="muted">No quote (job skipped or pending).</p>}
              </div>
            </div>
          </div>
        </>)}
    </Async>
  );
}
