import { useState } from "react";

export type Ev = { evidence_id: string; type: string; text: string; source?: string; date?: string | null; outcome?: string | null };

/** A proposal sentence; hover (or focus / tap) shows the portfolio evidence behind it. Keyboard accessible. */
export default function EvidenceHover({ text, evidence, label }: { text: string; evidence: Ev[]; label?: string }) {
  const [open, setOpen] = useState(false);
  const shown = text.replace(/\s*\[[^\]\s]+\]/g, "");
  if (!evidence.length) return <p className="para" data-testid="para-noevidence">{shown} {label && <span className="badge warn">{label}</span>}</p>;
  return (
    <div onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <p className="para has-ev" tabIndex={0} aria-expanded={open} onFocus={() => setOpen(true)} onBlur={() => setOpen(false)}
         onClick={() => setOpen((o) => !o)} onKeyDown={(e) => e.key === "Escape" && setOpen(false)} data-testid="para-evidence">
        {shown} <span className="badge ok">evidence: {evidence.map((e) => e.evidence_id).join(", ")}</span>
      </p>
      {open && (
        <div className="ev-pop" role="tooltip" data-testid="evidence-popover">
          {evidence.map((e) => (
            <div key={e.evidence_id}>
              <strong>{e.type.replace("_", " ")}</strong> <span className="muted">· {e.source ?? e.evidence_id}{e.date ? ` · ${e.date}` : ""}{e.outcome ? ` · ${e.outcome}` : ""}</span>
              <pre style={{ whiteSpace: "pre-wrap", margin: "4px 0 0", fontFamily: "inherit" }}>{e.text}</pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
