"""LLM-judge calibration (B4). The judge MUST agree with YOUR labels before any judge score is reported.

Step 1  python -m evals.runners.judge_calibration prepare
        -> evals/datasets/judge_labels.csv : 30 anonymised proposals + the judge's rubric score. YOU fill `human_score` (1-5).
Step 2  python -m evals.runners.judge_calibration compute
        -> Cohen's kappa (quadratic-weighted) and exact agreement between your labels and the judge
        -> evals/results/judge_calibration.json (refuses to run until all 30 human labels exist)

Judge: with an LLM profile configured it is a rubric prompt; in the offline profile it is the deterministic rubric
below (specificity, grounding, personalisation, length). Either way it is calibrated against YOUR labels; no label here
was filled in by the tooling.
"""
from __future__ import annotations

import asyncio
import csv
import json
import random
import re
import sys

from evals.runners._harness import PERSONAS, ROOT, Harness, dev

CSV = ROOT / "evals" / "datasets" / "judge_labels.csv"


def rubric_score(text: str, n_evidence: int, job_title: str) -> int:
    """1-5 deterministic rubric. Offline stand-in for an LLM judge (same interface)."""
    s = 1
    if len(text) >= 350:
        s += 1
    if n_evidence >= 1:
        s += 1
    if n_evidence >= 2:
        s += 1
    toks = [w for w in re.findall(r"[a-z]+", job_title.lower()) if len(w) > 3]
    if toks and any(w in text.lower() for w in toks):
        s += 1
    if re.search(r"hard-working|please hire me|dear sir", text, re.I):
        s = max(1, s - 2)
    return min(s, 5)


async def prepare(n: int = 30) -> None:
    h = Harness()
    rnd = random.Random(4016)
    items = []
    for persona in PERSONAS:
        for r in [x for x in dev(persona) if x["gold"]["decision"] == "bid"][:25]:
            o = await h.run(persona, r["job_id"])
            st = o["state"]
            if st.get("proposal_draft"):
                txt = st["compliance_verdict"]["cleaned_text"]
                items.append(dict(job=r["title"], text=txt, n_ev=len(st["proposal_draft"]["evidence_ids"])))
    rnd.shuffle(items)
    items = items[:n]
    CSV.parent.mkdir(parents=True, exist_ok=True)
    with CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["item", "job_title", "proposal_text", "judge_score", "human_score"])
        for i, it in enumerate(items):
            w.writerow([i + 1, it["job"], it["text"], rubric_score(it["text"], it["n_ev"], it["job"]), ""])
    print(f"wrote {CSV} ({len(items)} items). Fill the human_score column (1-5) yourself, then run: compute")


def qw_kappa(a: list[int], b: list[int], k: int = 5) -> float:
    n = len(a)
    obs = [[0] * k for _ in range(k)]
    for x, y in zip(a, b):
        obs[x - 1][y - 1] += 1
    ra = [sum(r) for r in obs]
    cb = [sum(obs[i][j] for i in range(k)) for j in range(k)]
    num = den = 0.0
    for i in range(k):
        for j in range(k):
            w = (i - j) ** 2 / (k - 1) ** 2
            num += w * obs[i][j]
            den += w * ra[i] * cb[j] / n
    return 1 - num / den if den else 1.0


def compute() -> None:
    rows = list(csv.DictReader(CSV.open(encoding="utf-8")))
    if any(not r["human_score"].strip() for r in rows) or len(rows) < 30:
        sys.exit(f"{CSV}: need 30 rows with a human_score each (found {sum(1 for r in rows if r['human_score'].strip())}). Label them yourself first.")
    h = [int(r["human_score"]) for r in rows]
    j = [int(r["judge_score"]) for r in rows]
    exact = sum(x == y for x, y in zip(h, j)) / len(h)
    within1 = sum(abs(x - y) <= 1 for x, y in zip(h, j)) / len(h)
    dis = sorted(range(len(h)), key=lambda i: -abs(h[i] - j[i]))[:2]
    out = dict(n=len(h), weighted_kappa=round(qw_kappa(h, j), 4), exact_agreement=round(exact, 4), within_one=round(within1, 4),
               biggest_disagreements=[dict(item=rows[i]["item"], human=h[i], judge=j[i], text=rows[i]["proposal_text"][:200]) for i in dis])
    (ROOT / "evals" / "results" / "judge_calibration.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    {"prepare": lambda: asyncio.run(prepare()), "compute": compute}[sys.argv[1] if len(sys.argv) > 1 else "prepare"]()
