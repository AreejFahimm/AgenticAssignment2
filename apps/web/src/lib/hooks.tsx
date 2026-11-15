import { useCallback, useEffect, useRef, useState } from "react";
import { getJson } from "./api/client";

export type Load<T> = { data: T | null; loading: boolean; error: string | null; reload: () => void };

/** Loading / error / data with a manual reload; optional polling. Every screen renders all three states. */
export function useLoad<T = any>(path: string | null, pollMs = 0): Load<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(!!path);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);
  const load = useCallback(() => {
    if (!path) return;
    getJson<T>(path)
      .then((d) => { if (alive.current) { setData(d); setError(null); } })
      .catch((e) => { if (alive.current) setError(String(e.message ?? e)); })
      .finally(() => { if (alive.current) setLoading(false); });
  }, [path]);
  useEffect(() => {
    alive.current = true;
    load();
    const t = pollMs ? setInterval(load, pollMs) : undefined;
    return () => { alive.current = false; if (t) clearInterval(t); };
  }, [load, pollMs]);
  return { data, loading, error, reload: load };
}

export function Async<T>({ s, children, empty }: { s: Load<T>; children: (d: T) => React.ReactNode; empty?: (d: T) => boolean }) {
  if (s.loading && !s.data) return <p className="muted" role="status">Loading…</p>;
  if (s.error && !s.data) {
    const down = /50[0-9]|Failed to fetch|NetworkError/.test(s.error);
    return (
      <div className="card" role="alert">
        <p className="error">{down ? "The server is not reachable right now." : s.error}</p>
        <button onClick={s.reload}>Retry</button>
      </div>
    );
  }
  if (s.data == null) return null;
  if (empty?.(s.data)) return <div className="empty">Nothing here yet.</div>;
  return <>{children(s.data)}</>;
}
