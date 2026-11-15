import { Link } from "react-router-dom";
import { Async, useLoad } from "../../lib/hooks";

const COLS = ["drafted", "submitted", "viewed", "replied", "interview", "hired", "lost"];

export default function Pipeline() {
  const s = useLoad<Record<string, any[]>>("/pipeline", 5000);
  return (
    <>
      <h1>Pipeline</h1>
      <p className="muted small">Cards move automatically as the marketplace reports views, replies and hires.</p>
      <Async s={s}>
        {(d) => (
          <div className="kanban" data-testid="kanban">
            {COLS.map((c) => (
              <section key={c} className="col" aria-label={c}>
                <h3>{c} ({(d[c] ?? []).length})</h3>
                {(d[c] ?? []).length === 0 && <div className="muted small">empty</div>}
                {(d[c] ?? []).map((i) => (
                  <div className="item" key={i.id}>
                    {i.thread_id ? <Link to={`/studio/${encodeURIComponent(i.thread_id)}`}>{i.title}</Link> : i.title}
                    <div className="muted">{i.category}{i.bid ? ` · $${i.bid}` : ""}</div>
                  </div>))}
              </section>))}
          </div>)}
      </Async>
    </>
  );
}
