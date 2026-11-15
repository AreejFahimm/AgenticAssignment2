import { useState } from "react";
import { getJson, sendJson } from "../../lib/api/client";
import { Async, useLoad } from "../../lib/hooks";

function Thread({ t, reload }: { t: any; reload: () => void }) {
  const [payload, setPayload] = useState<any>(null);
  const [text, setText] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const tid = t.conversation?.thread_id;

  async function draft() {
    setBusy(true); setErr(null);
    try {
      const r = await sendJson("POST", `/messages/${encodeURIComponent(t.proposal_id)}/draft`);
      for (let i = 0; i < 40; i++) {                        // poll until the interrupt payload exists
        await new Promise((res) => setTimeout(res, 400));
        try { const p = await getJson(`/approvals/${encodeURIComponent(r.thread_id)}`); setPayload({ ...p, thread_id: r.thread_id }); setText(p.draft_reply); break; } catch { /* not ready */ }
      }
    } catch (e: any) { setErr(String(e.message)); } finally { setBusy(false); }
  }
  async function send(status: "approved" | "edited" | "rejected") {
    setBusy(true);
    try {
      await sendJson("POST", `/approvals/${encodeURIComponent(payload.thread_id)}`, status === "edited" ? { status, edited_text: text } : status === "rejected" ? { status, reason: "not needed" } : { status });
      setPayload(null); reload();
    } catch (e: any) { setErr(String(e.message)); } finally { setBusy(false); }
  }
  return (
    <div className="card" data-testid="thread">
      <div className="row spread"><strong>{t.title}</strong><span className="badge">{t.status}</span></div>
      <ul className="small">{t.messages.map((m: any, i: number) => <li key={i}><b>{m.from}:</b> {m.text}</li>)}</ul>
      {!payload && <button disabled={busy} onClick={draft} data-testid="draft-reply">Suggest a reply</button>}
      {payload && (
        <div data-testid="reply-approval">
          <p className="small"><span className="badge">{payload.intent}</span> {payload.risk_flags?.map((f: string) => <span key={f} className="badge bad">{f}</span>)}</p>
          {payload.slots?.length > 0 && <p className="small">Proposed slots: {payload.slots.map((s: any) => s.start).join(" · ")}</p>}
          <label htmlFor={`r-${t.proposal_id}`}>Suggested reply (editable)</label>
          <textarea id={`r-${t.proposal_id}`} style={{ minHeight: 100 }} value={text} onChange={(e) => setText(e.target.value)} />
          <div className="row"><button className="primary" disabled={busy} onClick={() => send(text.trim() !== payload.draft_reply.trim() ? "edited" : "approved")} data-testid="send-reply">Approve and send</button>
            <button disabled={busy} onClick={() => send("rejected")}>Discard</button></div>
        </div>)}
      {err && <p className="error" role="alert">{err}</p>}
    </div>
  );
}

export default function Messages() {
  const s = useLoad<any[]>("/messages", 6000);
  return (
    <>
      <h1>Messages</h1>
      <p className="muted small">Client messages are treated as untrusted. Replies are only sent after you approve them.</p>
      <Async s={s} empty={(d) => d.length === 0}>{(d) => <>{d.map((t) => <Thread key={t.proposal_id} t={t} reload={s.reload} />)}</>}</Async>
    </>
  );
}
