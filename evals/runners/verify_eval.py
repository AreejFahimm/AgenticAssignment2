"""Claim-verification evaluation (B3): unsupported-claim rate BEFORE vs AFTER verification, and verifier accuracy.

The offline writer is extractive (it cannot invent claims), so to test the verifier we plant FABRICATED experience
sentences into real drafts (templates below) and measure how many it removes (recall) and how many true claims it
wrongly removes (false-positive rate). Planted fabrications are synthetic and labelled; with an LLM Writer profile
the same script is run on its natural drafts to report the real unsupported-claim rate.

    python -m evals.runners.verify_eval [--per-persona 30]  ->  evals/results/verification.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import re

from evals.runners._harness import PERSONAS, ROOT, Harness, dev
from rag.verify import apply_verification, unsupported_rate, verify_claims

FABRICATIONS = [
    "I led a team of 12 engineers at Google for 6 years.",
    "I have 9 years of experience deploying Kubernetes clusters for Fortune 500 clients.",
    "I increased revenue by 340% for a client in the first month.",
    "I built a platform serving 50 million users per day.",
    "I delivered a blockchain product that raised 20 million dollars.",
    "I worked for NASA as a lead developer.",
    "On a past project, I achieved 99.99% accuracy on every benchmark.",
]


async def main(per_persona: int) -> dict:
    h = Harness()
    rnd = random.Random(4016)
    n_drafts = true_claims = fp = fab_total = fab_removed = 0
    before_rates, after_rates = [], []
    for persona in PERSONAS:
        for r in [x for x in dev(persona) if x["gold"]["decision"] == "bid"][:per_persona]:
            out = await h.run(persona, r["job_id"])
            st = out["state"]
            if not st.get("proposal_draft"):
                continue
            ev = st.get("evidence", [])
            sents = [s for s in re.split(r"(?<=[.!?])\s+", re.sub(r"\s*\[[^\]\s]+\]", "", st["proposal_draft"]["cover_letter"])) if s]
            fabs = rnd.sample(FABRICATIONS, 2)
            mixed = sents[:2] + fabs + sents[2:]
            draft = " ".join(mixed)
            v = verify_claims(draft, ev)
            before_rates.append(unsupported_rate(v))
            kept = apply_verification(draft, v)
            v2 = verify_claims(kept, ev)
            after_rates.append(unsupported_rate(v2))
            n_drafts += 1
            for item in v:
                if item["claim"] in fabs:
                    fab_total += 1
                    fab_removed += item["label"] == "unsupported"
                elif item["label"] != "not_a_claim":
                    true_claims += 1
                    fp += item["label"] == "unsupported"
    return dict(drafts=n_drafts, fabricated_planted=fab_total, fabricated_removed=fab_removed,
                fabrication_recall=round(fab_removed / fab_total, 4) if fab_total else None,
                true_claims_checked=true_claims, true_claims_wrongly_removed=fp,
                false_positive_rate=round(fp / true_claims, 4) if true_claims else None,
                unsupported_rate_before=round(sum(before_rates) / len(before_rates), 4), unsupported_rate_after=round(sum(after_rates) / len(after_rates), 4),
                method="planted synthetic fabrications into extractive drafts (offline writer cannot fabricate)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-persona", type=int, default=30)
    a = ap.parse_args()
    res = asyncio.run(main(a.per_persona))
    print(res)
    (ROOT / "evals" / "results" / "verification.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
