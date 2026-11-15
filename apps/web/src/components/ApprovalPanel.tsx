import { useState } from "react";
import { sendJson } from "../lib/api/client";

/** Approve / edit / reject. Resumes the interrupted LangGraph thread. Shows the dry_run preview (what will be sent + cost). */
export default function ApprovalPanel({ threadId, payload, onDone }: { threadId: string; payload: any; onDone: () => void }) {
  const [edited, setEdited] = useState<string>(payload.final_text);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(payload.error ?? null);
  const [mode, setMode] = useState<"view" | "reject">("view");
  const p = payload.dry_run_preview;
  const changed = edited.trim() !== payload.final_text.trim();

  async function decide(body: any) {
    setBusy(true); setErr(null);
    try { await sendJson("POST", `/approvals/${encodeURIComponent(threadId)}`, body); onDone(); }
    catch (e: any) { setErr(String(e.message ?? e)); }
    finally { setBusy(false); }
  }
  return (
    <section className="card" aria-labelledby="approval-h" data-testid="approval-panel">
      <h2 id="approval-h">Approval required</h2>
      <p className="muted small">Nothing is sent until you approve. After approving, you still confirm on the marketplace where required.</p>
      <div className="card" data-testid="dry-run">
        <strong>Preview (dry run)</strong>
        <div className="small">Will send a proposal for <b>{p?.preview?.bid_amount}</b> USD · costs <b data-testid="connects-cost">{p?.connects_cost}</b> Connects ·
          balance {p?.balance} → <b>{p?.balance_after}</b>{p?.over_weekly_budget && <span className="badge bad"> over weekly budget</span>}</div>
      </div>
      <label htmlFor="final-text">Cover letter (editable)</label>
      <textarea id="final-text" data-testid="edit-text" value={edited} onChange={(e) => setEdited(e.target.value)} />
      {changed && <p className="small muted">Your edits are diffed, re-checked by Compliance, and used to learn your style (only if you repeat them).</p>}
      {payload.compliance?.violations?.length > 0 && <p className="small"><span className="badge warn">Compliance</span> {payload.compliance.violations.join("; ")}</p>}
      {err && <p className="error" role="alert" data-testid="approval-error">{err}</p>}
      {mode === "reject" ? (
        <div>
          <label htmlFor="reason">Why reject? (used to improve future drafts)</label>
          <input id="reason" data-testid="reject-reason" value={reason} onChange={(e) => setReason(e.target.value)} />
          <div className="row" style={{ marginTop: 8 }}>
            <button className="danger" disabled={busy || !reason.trim()} data-testid="confirm-reject" onClick={() => decide({ status: "rejected", reason })}>Confirm reject</button>
            <button onClick={() => setMode("view")}>Cancel</button>
          </div>
        </div>
      ) : (
        <div className="row">
          <button className="primary" disabled={busy || changed} data-testid="approve" onClick={() => decide({ status: "approved" })}>Approve</button>
          <button disabled={busy || !changed} data-testid="save-edit" onClick={() => decide({ status: "edited", edited_text: edited })}>Approve with my edits</button>
          <button className="danger" disabled={busy} data-testid="reject" onClick={() => setMode("reject")}>Reject…</button>
        </div>
      )}
    </section>
  );
}
