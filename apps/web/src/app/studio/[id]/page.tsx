import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import ApprovalPanel from "../../../components/ApprovalPanel";
import EvidenceHover from "../../../components/EvidenceHover";
import { sendJson } from "../../../lib/api/client";
import { Async, useLoad } from "../../../lib/hooks";

export default function Studio() {
  const { id = "" } = useParams();
  const enc = encodeURIComponent(id);
  const studio = useLoad<any>(`/proposals/${enc}`);
  const approval = useLoad<any>(`/approvals/${enc}`);
  const [regen, setRegen] = useState<Record<number, string>>({});
  const [done, setDone] = useState(false);

  async function regenerate(i: number) {
    const r = await sendJson("POST", `/proposals/${enc}/regenerate`, { paragraph_index: i });
    setRegen((m) => ({ ...m, [i]: r.text }));
  }
  if (done) return <div className="card" role="status" data-testid="decision-sent"><h1>Decision recorded</h1><p>The graph resumed. <Link to="/inbox">Back to inbox</Link> · <Link to={`/runs/${enc}`}>View run</Link></p></div>;
  return (
    <Async s={studio}>
      {(d) => (
        <>
          <div className="row spread"><h1>Proposal studio</h1><Link to={`/jobs/${enc}`}>Job detail</Link></div>
          <p className="muted small">Hover, focus or tap a highlighted sentence to see the portfolio evidence behind it. Sentences without evidence are not experience claims.</p>
          <div className="two">
            <div>
              <div className="card" data-testid="draft">
                {d.paragraphs.map((p: any, i: number) => (
                  <div key={i}>
                    <EvidenceHover text={regen[i] ?? p.text} evidence={regen[i] ? d.evidence.filter((e: any) => regen[i].includes(`[${e.evidence_id}]`)) : p.evidence} />
                    {p.evidence.length > 0 && <button className="small" aria-label={`Regenerate paragraph ${i + 1}`} onClick={() => regenerate(i)}>Regenerate this paragraph</button>}
                  </div>))}
                {Object.keys(regen).length > 0 && <p className="small muted">Regenerated text is a suggestion: copy it into the editor below before approving.</p>}
              </div>
              {approval.error && !approval.data && <div className="card"><p className="muted">Nothing is waiting for approval on this thread ({d.status}).</p></div>}
              {approval.data && <ApprovalPanel threadId={id} payload={approval.data} onDone={() => setDone(true)} />}
            </div>
            <div>
              <div className="card"><h2>Critic</h2>
                {d.critiques.map((c: any, i: number) => (<div key={i} className="small"><span className={`badge ${c.passed ? "ok" : "warn"}`}>round {i + 1}: {c.passed ? "passed" : "sent back"}</span>
                  <ul>{c.issues.map((x: string) => <li key={x}>{x}</li>)}</ul></div>))}</div>
              <div className="card"><h2>Compliance</h2>
                <span className={`badge ${d.compliance?.passed ? "ok" : "bad"}`}>{d.compliance?.passed ? "passed" : "blocked"}</span>
                <ul className="small">{(d.compliance?.violations ?? []).map((v: string) => <li key={v}>{v}</li>)}</ul>{d.compliance?.reason && <p className="error small">{d.compliance.reason}</p>}</div>
              <div className="card"><h2>Claim check</h2>
                <ul className="small" data-testid="claims">{d.claim_verification.filter((c: any) => c.label !== "not_a_claim").map((c: any, i: number) => (
                  <li key={i}><span className={`badge ${c.label === "supported" ? "ok" : c.label === "partly_supported" ? "warn" : "bad"}`}>{c.label}</span> {c.claim}</li>))}</ul></div>
            </div>
          </div>
        </>)}
    </Async>
  );
}
