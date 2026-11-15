"""Per-category / per-skill market price statistics -> data/processed/price_stats.json.

Sources (best effort): processed jobs (always) + contracts dataset if present in data/raw/.
Each stat records `n` and the sources used so the data card can cite exactly what fed it.
"""
from __future__ import annotations

import sys
from collections import defaultdict

import pandas as pd

from common import PROCESSED, RAW, categorize, extract_skills, read_jsonl, write_json


def q(vals: list[float], p: float) -> float:
    s = sorted(vals)
    return s[min(int(p * (len(s) - 1) + 0.5), len(s) - 1)]


def summarize(vals: list[float]) -> dict:
    return {"n": len(vals), "p25": round(q(vals, .25), 2), "median": round(q(vals, .5), 2),
            "p75": round(q(vals, .75), 2)}


def main() -> int:
    buckets: dict[tuple[str, str], list[float]] = defaultdict(list)
    sources: set[str] = set()
    jp = PROCESSED / "jobs.jsonl"
    if jp.exists():
        for j in read_jsonl(jp):
            b = j["budget"]
            v = b.get("min") or b.get("max")
            if not v or v <= 0:
                continue
            sources.add(j["provenance"].split(":", 1)[1] if ":" in j["provenance"] else j["provenance"])
            k = "hourly" if b["type"] == "hourly" else "fixed"
            buckets[(k, "cat:" + j["category"])].append(float(v))
            for s in j["required_skills"]:
                buckets[(k, "skill:" + s)].append(float(v))
    # Title-only job file (no description): upwork-all-jobs-200k -> hourly_low/high or budget by title
    adir = RAW / "upwork-all-jobs-200k"
    for f in (sorted(adir.rglob("*.csv")) if adir.exists() else []):
        df = pd.read_csv(f, on_bad_lines="skip", low_memory=False)
        print(f"all-jobs {f.name}: rows={len(df)} cols={list(df.columns)}")
        sources.add("upwork-all-jobs-200k")
        for t, hl, hh, bud, ih in zip(df["title"].fillna("").astype(str), df.get("hourly_low"), df.get("hourly_high"),
                                      df.get("budget"), df.get("is_hourly")):
            cat = categorize(t)
            if cat == "other":
                continue
            sk = extract_skills(t)
            vals = []
            if str(ih).lower() == "true":
                v = pd.to_numeric(hl, errors="coerce")
                kind = "hourly"
            else:
                v = pd.to_numeric(bud, errors="coerce")
                kind = "fixed"
            if pd.notna(v) and v > 0:
                buckets[(kind, "cat:" + cat)].append(float(v))
                for s_ in sk:
                    buckets[(kind, "skill:" + s_)].append(float(v))
    # Contracts: job_title, total_paid, hourly_rate
    cdir = RAW / "freelance-contracts-1-3m"
    for f in (sorted(cdir.rglob("*.csv")) if cdir.exists() else []):
        df = pd.read_csv(f, on_bad_lines="skip", low_memory=False)
        print(f"contracts {f.name}: rows={len(df)} cols={list(df.columns)}")
        sources.add("freelance-contracts-1-3m")
        for t, paid, rate in zip(df["job_title"].fillna("").astype(str), pd.to_numeric(df["total_paid"], errors="coerce"),
                                 pd.to_numeric(df["hourly_rate"], errors="coerce")):
            cat = categorize(t)
            if cat == "other":
                continue
            if pd.notna(rate) and rate > 0:
                kind, v = "hourly", float(rate)
            elif pd.notna(paid) and paid > 0:
                kind, v = "fixed", float(paid)
            else:
                continue
            buckets[(kind, "cat:" + cat)].append(v)
            for s_ in extract_skills(t):
                buckets[(kind, "skill:" + s_)].append(v)
    out: dict = {"sources": sorted(sources), "stats": {}}
    for (kind, key), vals in buckets.items():
        if len(vals) >= 5:
            out["stats"].setdefault(key, {})[kind] = summarize(vals)
    write_json(PROCESSED / "price_stats.json", out)
    print(f"price stats for {len(out['stats'])} keys from {sorted(sources)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
