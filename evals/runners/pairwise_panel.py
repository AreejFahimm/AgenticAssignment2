"""Blind pairwise human panel (B4): classmates pick the better of two anonymised proposals.

    python -m evals.runners.pairwise_panel prepare   -> evals/datasets/pairwise_panel.csv   (give it to classmates; no variant names)
    python -m evals.runners.pairwise_panel tally     -> evals/results/pairwise_panel.json   (after classmates fill the `winner` column with A or B)

Arms compared: the shipped writer pipeline vs the generic control letter, for the same jobs. The A/B position is randomised with a fixed seed and the
key mapping is stored separately (evals/datasets/pairwise_key.json), so raters are blind. No judgement here is filled in by the tooling.
"""
from __future__ import annotations

import asyncio
import csv
import json
import random
import sys

from evals.runners._harness import PERSONAS, ROOT, Harness, dev

CSV = ROOT / "evals" / "datasets" / "pairwise_panel.csv"
KEY = ROOT / "evals" / "datasets" / "pairwise_key.json"
GENERIC = "Hello, I am a hard-working professional and I can do this job. Please hire me."


async def prepare(n: int = 30) -> None:
    h = Harness()
    rnd = random.Random(4016)
    rows, key = [], {}
    for persona in PERSONAS:
        for r in [x for x in dev(persona) if x["gold"]["decision"] == "bid"][: n // 3 + 5]:
            st = (await h.run(persona, r["job_id"]))["state"]
            if not st.get("compliance_verdict"):
                continue
            ours, base = st["compliance_verdict"]["cleaned_text"], GENERIC
            flip = rnd.random() < 0.5
            a, b = (base, ours) if flip else (ours, base)
            rid = len(rows) + 1
            key[rid] = {"A": "generic" if flip else "gigbid", "B": "gigbid" if flip else "generic"}
            rows.append([rid, r["title"], r["description"][:600], a, b, ""])
    rnd.shuffle(rows)
    rows = rows[:n]
    with CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["pair", "job_title", "job_excerpt", "proposal_A", "proposal_B", "winner"])
        w.writerows(rows)
    KEY.write_text(json.dumps(key), encoding="utf-8")
    print(f"wrote {CSV} ({len(rows)} pairs); classmates fill `winner` with A or B")


def tally() -> None:
    key = json.loads(KEY.read_text(encoding="utf-8"))
    rows = [r for r in csv.DictReader(CSV.open(encoding="utf-8")) if r["winner"].strip().upper() in ("A", "B")]
    if not rows:
        sys.exit("no completed rows: have classmates fill the winner column first")
    wins = sum(key[r["pair"]][r["winner"].strip().upper()] == "gigbid" for r in rows)
    out = dict(n=len(rows), gigbid_win_rate=round(wins / len(rows), 4), raters_note="count raters yourself and report how many classmates took part")
    (ROOT / "evals" / "results" / "pairwise_panel.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    {"prepare": lambda: asyncio.run(prepare()), "tally": tally}[sys.argv[1] if len(sys.argv) > 1 else "prepare"]()
