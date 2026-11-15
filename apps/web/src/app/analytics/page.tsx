import { Async, useLoad } from "../../lib/hooks";

export default function Analytics() {
  const s = useLoad<any>("/analytics", 10000);
  return (
    <>
      <h1>Analytics</h1>
      <Async s={s}>
        {(d) => (
          <>
            <div className="grid">
              <div className="card"><h2>Funnel</h2><p>Analysed <b>{d.funnel.analysed}</b> · skipped <b>{d.funnel.skipped}</b> · bid <b>{d.funnel.bid}</b> · submitted <b>{d.funnel.submitted}</b></p></div>
              <div className="card"><h2>Connects</h2><p>Spent <b>{d.connects.spent}</b> of weekly budget <b>{d.connects.budget}</b></p>
                <div className="bar"><i style={{ width: `${Math.min(100, (d.connects.spent / Math.max(d.connects.budget, 1)) * 100)}%` }} /></div></div>
              <div className="card"><h2>Cost and latency per proposal</h2><p>p95 latency <b>{d.cost_latency.p95_latency_s}s</b> · avg tokens <b>{d.cost_latency.avg_tokens}</b> · avg cost <b>${d.cost_latency.avg_usd}</b> <span className="muted small">({d.cost_latency.proposals} proposals)</span></p></div>
            </div>
            <div className="card table-wrap"><h2>Reply and hire rate by category</h2>
              {Object.keys(d.by_category).length === 0 ? <p className="muted">No submitted proposals yet.</p> :
                <table data-testid="by-category"><thead><tr><th>Category</th><th>Submitted</th><th>Replied</th><th>Hired</th><th>Reply rate</th><th>Hire rate</th><th>Connects</th></tr></thead>
                  <tbody>{Object.entries<any>(d.by_category).map(([k, v]) => <tr key={k}><td>{k}</td><td>{v.submitted}</td><td>{v.replied}</td><td>{v.hired}</td><td>{v.reply_rate ?? "–"}</td><td>{v.hire_rate ?? "–"}</td><td>{v.connects}</td></tr>)}</tbody></table>}
            </div>
            <div className="card"><h2>Top rejection reasons</h2>
              {d.top_rejection_reasons.length === 0 ? <p className="muted">None yet.</p> : <ol data-testid="rejections">{d.top_rejection_reasons.map((r: any) => <li key={r.reason}>{r.reason} <span className="badge">{r.count}</span></li>)}</ol>}
            </div>
          </>)}
      </Async>
    </>
  );
}
