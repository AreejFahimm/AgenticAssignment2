"""Failure analysis (report section 8): collect REAL failed dev jobs and classify them.

    python -m evals.runners.failed_jobs  ->  evals/results/failed_jobs.json

Classes: wrong_skip (gold bid, we skipped/watched), wrong_bid (gold skip, we bid), mispriced (bid outside the market band),
missed_evidence (bid job whose gold evidence has no overlap with retrieved evidence). Each row keeps job id, title, the
decision reasons and the trace-relevant numbers so it can be opened in the app/trace.
"""
from __future__ import annotations

import asyncio
import json

from evals.runners._harness import PERSONAS, ROOT, Harness, dev


async def main(per_persona: int = 40) -> dict:
    h = Harness()
    rows = []
    for persona in PERSONAS:
        for r in dev(persona)[:per_persona]:
            st = (await h.run(persona, r["job_id"]))["state"]
            dec = st.get("decision") or {}
            pred_bid = dec.get("action") == "bid" and st.get("status") in ("waiting_approval", "blocked")
            gold_bid = r["gold"]["decision"] == "bid"
            cls = None
            if gold_bid and not pred_bid:
                cls = "wrong_skip"
            elif pred_bid and not gold_bid:
                cls = "wrong_bid"
            elif pred_bid and r["gold"]["fair_price_band"] and st.get("price_quote"):
                b, q = r["gold"]["fair_price_band"], st["price_quote"]["bid_amount"]
                if not b["low"] <= q <= b["high"]:
                    cls = "mispriced"
            if cls is None and pred_bid and r["gold"]["relevant_evidence"]:
                got = set((st.get("fit_report") or {}).get("evidence_ids", []))
                if not got & set(r["gold"]["relevant_evidence"]):
                    cls = "missed_evidence"
            if cls:
                rows.append(dict(cls=cls, persona=persona, job_id=r["job_id"], title=r["title"][:80], decision=dec.get("action"),
                                 reasons=dec.get("reasons"), fit=(st.get("fit_report") or {}).get("score"), skill_overlap=r["gold"]["skill_overlap"],
                                 bid=(st.get("price_quote") or {}).get("bid_amount"), band=r["gold"]["fair_price_band"] and [r["gold"]["fair_price_band"]["low"], r["gold"]["fair_price_band"]["high"]]))
    by = {}
    for r in rows:
        by.setdefault(r["cls"], []).append(r)
    picked = []
    for cls in ("wrong_skip", "wrong_bid", "mispriced", "missed_evidence"):
        picked += by.get(cls, [])[:4]
    return dict(counts={k: len(v) for k, v in by.items()}, examples=picked[:12], jobs_examined=per_persona * len(PERSONAS))


if __name__ == "__main__":
    out = asyncio.run(main())
    (ROOT / "evals" / "results" / "failed_jobs.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out["counts"]))
    for e in out["examples"]:
        print(e["cls"], e["persona"], e["job_id"], "|", e["title"], "|", e["reasons"], "| fit", e["fit"], "overlap", e["skill_overlap"], "bid", e["bid"], "band", e["band"])
