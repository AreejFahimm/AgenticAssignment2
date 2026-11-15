import { useEffect, useState } from "react";
import { API_BASE, getToken } from "../lib/api/client";

type Ev = { id: number; kind: string; data: any };

/** Live node-by-node progress streamed over Server-Sent Events from LangGraph (stream_mode=updates). */
export default function RunTimeline({ threadId, onDone }: { threadId: string; onDone?: () => void }) {
  const [events, setEvents] = useState<Ev[]>([]);
  const [state, setState] = useState<"live" | "done" | "error">("live");
  useEffect(() => {
    const ctl = new AbortController();
    let last = 0;
    (async () => {
      try {
        const r = await fetch(`${API_BASE}/runs/${encodeURIComponent(threadId)}/events?after=${last}`, { headers: { Authorization: `Bearer ${getToken()}` }, signal: ctl.signal });
        if (!r.ok || !r.body) throw new Error(String(r.status));
        const reader = r.body.getReader(); const dec = new TextDecoder(); let buf = "";
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          let i: number;
          while ((i = buf.indexOf("\n\n")) >= 0) {
            const chunk = buf.slice(0, i); buf = buf.slice(i + 2);
            const id = /^id: (\d+)/m.exec(chunk)?.[1]; const kind = /^event: (.+)$/m.exec(chunk)?.[1]; const data = /^data: (.+)$/m.exec(chunk)?.[1];
            if (id && kind && data) { last = +id; setEvents((e) => [...e, { id: +id, kind, data: JSON.parse(data) }]); }
          }
        }
        setState("done"); onDone?.();
      } catch (e: any) { if (e.name !== "AbortError") setState("error"); }
    })();
    return () => ctl.abort();
  }, [threadId]);
  return (
    <div data-testid="run-timeline">
      <p className="muted small" role="status">{state === "live" ? "Streaming live…" : state === "done" ? "Run finished." : "Stream interrupted. Reload to reconnect."}</p>
      {events.length === 0 && state === "live" && <p className="muted">Waiting for the first agent…</p>}
      <ol className="timeline">
        {events.map((e) => (
          <li key={e.id}>
            <span className={`dot ${e.kind === "interrupt" ? "wait" : e.kind === "error" || e.kind === "degraded" ? "err" : ""}`} aria-hidden />
            <div>
              <strong>{e.kind === "node" ? e.data.node : e.kind === "interrupt" ? "Waiting for your approval" : e.kind}</strong>{" "}
              {e.kind === "node" && <span className="muted small">{e.data.ms} ms</span>}
              {e.kind === "node" && e.data.detail && <div className="small muted">{Object.entries(e.data.detail).filter(([k]) => !["node", "ms"].includes(k)).map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : v}`).join(" · ")}</div>}
              {(e.kind === "error" || e.kind === "degraded") && <div className="error small">{e.data.error}</div>}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
