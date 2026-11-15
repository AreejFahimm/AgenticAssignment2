import { useState } from "react";
import { sendJson } from "../lib/api/client";
import { useLoad } from "../lib/hooks";

/** "Marketplace unavailable" degraded-mode banner (viva item 1). Polls /status; the work is queued server-side. */
export default function StatusBanner() {
  const s = useLoad<any>("/status", 5000);
  const [busy, setBusy] = useState(false);
  if (s.error) {  // polled: the first failed poll after a success means the server went away
    return <div className="banner bad" role="alert" data-testid="api-down-banner">GigBid server is unreachable. Your pending approvals are safe and will reappear when it is back.</div>;
  }
  if (!s.data || s.data.marketplace_ok) return null;
  return (
    <div className="banner bad" role="alert" data-testid="degraded-banner">
      Marketplace unavailable. Your work is queued and will resume automatically when it is back
      {s.data.queued_degraded ? ` (${s.data.queued_degraded} queued)` : ""}.{" "}
      <button disabled={busy} onClick={async () => { setBusy(true); try { await sendJson("POST", "/status/check"); } finally { setBusy(false); s.reload(); } }}>Retry now</button>
    </div>
  );
}
