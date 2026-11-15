"""X2 Signature extension: proposal experiments. Two writer strategies A/B-tested in GigSim with a significance test.

    python -m evals.runners.ab_experiment [--per-persona 25]  ->  evals/results/ab_experiment.json

A = evidence_first (up to 3 cited past-work sentences, honest gaps, milestone offer)
B = concise_question (one cited sentence + a clarifying question to the client)
PAIRED design: the same jobs get both strategies (separate marketplace users so Connects never interact). Replies in
GigSim-local are deterministic per proposal id, so differences come from the letter. Tests: McNemar exact (paired) and a
two-proportion z-test; plus a 95% bootstrap CI on the reply-rate difference. Honest scope: GigSim-local clients are
rule-based (skill mentions + genericness + price), so this measures the simulator's preferences, not real clients.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import random

from evals.runners._harness import PERSONAS, ROOT, Harness, dev

STRATS = ("evidence_first", "concise_question")


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact binomial p for discordant pairs (b = A-only replies, c = B-only replies)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def two_prop_z(x1: int, n1: int, x2: int, n2: int) -> tuple[float, float]:
    p = (x1 + x2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2)) if 0 < p < 1 else 0
    z = ((x1 / n1) - (x2 / n2)) / se if se else 0.0
    return z, 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))


async def main(per_persona: int) -> dict:
    h = Harness()
    pairs = []
    for persona in PERSONAS:
        for r in [x for x in dev(persona) if x["gold"]["decision"] == "bid"][:per_persona]:
            res = {}
            for s in STRATS:
                out = await h.run(persona, r["job_id"], user=f"ab-{s}-{persona}", approve=True, strategy=s)
                sub = out["state"].get("submission")
                res[s] = None if not sub else sub["status"] in ("replied", "interview", "hired")
            if all(v is not None for v in res.values()):
                pairs.append((persona, res["evidence_first"], res["concise_question"]))
    n = len(pairs)
    a = sum(p[1] for p in pairs)
    b = sum(p[2] for p in pairs)
    a_only = sum(p[1] and not p[2] for p in pairs)
    b_only = sum(p[2] and not p[1] for p in pairs)
    z, pz = two_prop_z(a, n, b, n)
    rnd = random.Random(4016)
    diffs = []
    for _ in range(2000):
        sm = [pairs[rnd.randrange(n)] for _ in range(n)]
        diffs.append(sum(x[1] for x in sm) / n - sum(x[2] for x in sm) / n)
    diffs.sort()
    return dict(n_pairs=n, reply_rate_A_evidence_first=round(a / n, 4), reply_rate_B_concise_question=round(b / n, 4),
                diff_A_minus_B=round(a / n - b / n, 4), bootstrap_95ci=[round(diffs[50], 4), round(diffs[1949], 4)],
                discordant=dict(A_only=a_only, B_only=b_only), mcnemar_exact_p=round(mcnemar_exact(a_only, b_only), 5),
                two_proportion_z=round(z, 3), two_proportion_p=round(pz, 5),
                significant_at_0_05=mcnemar_exact(a_only, b_only) < 0.05,
                by_persona={p: dict(n=sum(1 for x in pairs if x[0] == p), A=sum(x[1] for x in pairs if x[0] == p), B=sum(x[2] for x in pairs if x[0] == p)) for p in PERSONAS},
                caveat="GigSim-local clients are rule-based; this tests the experiment machinery and simulator preferences, not real clients")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-persona", type=int, default=25)
    a = ap.parse_args()
    out = asyncio.run(main(a.per_persona))
    print(json.dumps(out, indent=2))
    (ROOT / "evals" / "results" / "ab_experiment.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
