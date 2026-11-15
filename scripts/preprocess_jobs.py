"""Normalise Kaggle job datasets into one Job schema -> data/processed/jobs.jsonl.

Usage:  python scripts/preprocess_jobs.py [--max-rows 60000] [--synthetic-fallback] [--report]
Column names differ between datasets, so we map by alias lists. After downloading, run with
--report to print the detected columns per file and CHECK them; adjust ALIASES if needed.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import re
import sys

import pandas as pd

from common import (PROCESSED, RAW, REAL, categorize, extract_skills, mask_pii,
                    persona_for_category, stable_id, write_jsonl)
from synth_jobs import gen_jobs

JOB_FOLDERS = ["upwork-jobs-2024-50k", "upwork-all-jobs-200k", "upwork-freelance-jobs-60k"]
ALIASES = {
    "title": ["title", "job_title", "name", "job"],
    "description": ["description", "desc", "job_description", "text", "details"],
    "skills": ["skills", "skill", "tags", "required_skills", "categories"],
    "budget": ["budget", "fixed_price", "fixed_budget", "amount", "price", "client_budget"],
    "hourly_low": ["hourly_low", "hourly_min", "hourly_rate_min", "min_hourly", "hourly_rate_from"],
    "hourly_high": ["hourly_high", "hourly_max", "hourly_rate_max", "max_hourly", "hourly_rate_to"],
    "is_hourly": ["is_hourly", "hourly", "job_type", "type", "payment_type"],
    "country": ["country", "client_country", "location"],
    "posted": ["published_date", "date_posted", "posted_at", "date", "job_ts", "created_at", "published"],
}
_TAG = re.compile(r"<[^>]+>")


def pick(cols: list[str], key: str) -> str | None:
    low = {c.lower().strip(): c for c in cols}
    for a in ALIASES[key]:
        if a in low:
            return low[a]
    return None


def num(v) -> float | None:
    try:
        f = float(str(v).replace("$", "").replace(",", ""))
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def clean(text) -> str:
    t = html.unescape(_TAG.sub(" ", str(text or "")))
    return re.sub(r"\s+", " ", t).strip()


_TRAILER = re.compile(r"(Budget:|Hourly Range:|Posted On:)")
_LISTED = re.compile(r"Skills:\s*(.*?)(?=Skills:|Country:|click to apply|$)")


def split_trailer(desc: str) -> tuple[str, list[str]]:
    """Real posts end with 'Budget:.. Posted On:.. Category:.. Skills:a, b Country:.. click to apply' boilerplate."""
    m = _TRAILER.search(desc)
    body = desc[: m.start()].strip() if m else desc
    listed: list[str] = []
    for lm in _LISTED.finditer(desc):
        listed += [x.strip() for x in lm.group(1).split(",") if x.strip()]
    return body, sorted(set(listed))


def english_ratio(t: str) -> float:
    return sum(c.isascii() for c in t) / max(len(t), 1)


def norm_hash(title: str, desc: str) -> str:
    key = re.sub(r"[^a-z0-9]", "", (title + desc[:300]).lower())
    return hashlib.md5(key.encode()).hexdigest()


def load_folder(folder: str, max_rows: int, report: bool) -> list[dict]:
    rows: list[dict] = []
    for f in sorted((RAW / folder).rglob("*.csv")):
        try:
            df = pd.read_csv(f, nrows=max_rows, on_bad_lines="skip", low_memory=False)
        except Exception as e:  # noqa: BLE001
            print(f"  skip {f.name}: {e}", file=sys.stderr)
            continue
        cols = list(df.columns)
        m = {k: pick(cols, k) for k in ALIASES}
        if report:
            print(f"[{folder}] {f.name} rows={len(df)} cols={cols}\n   mapping={m}")
        if not m["title"] or not m["description"]:
            print(f"  {f.name}: no title/description column, skipped (extend ALIASES)", file=sys.stderr)
            continue
        for _, r in df.iterrows():
            title, desc = clean(r[m["title"]]), clean(r[m["description"]])
            desc, listed = split_trailer(desc)
            if len(desc) < 150 or english_ratio(title + desc) < 0.92:
                continue
            hourly = False
            if m["is_hourly"]:
                hourly = str(r[m["is_hourly"]]).lower() in ("true", "1", "hourly", "yes")
            lo = num(r[m["hourly_low"]]) if m["hourly_low"] else None
            hi = num(r[m["hourly_high"]]) if m["hourly_high"] else None
            fixed = num(r[m["budget"]]) if m["budget"] else None
            if lo or hi:
                hourly = True
            budget = ({"type": "hourly", "min": lo or hi, "max": hi or lo, "currency": "USD"} if hourly
                      else {"type": "fixed", "min": fixed, "max": fixed, "currency": "USD"})
            raw_sk = str(r[m["skills"]]) if m["skills"] and pd.notna(r[m["skills"]]) else ""
            skills = sorted(set(extract_skills(f"{title} {desc} {raw_sk} {' '.join(listed)}")))
            cat = categorize(f"{title} {raw_sk} {desc[:400]}")
            if cat == "other" or not skills:
                continue
            rows.append({
                "job_id": stable_id("job", folder, title, desc[:80]),
                "title": mask_pii(title), "description": mask_pii(desc),
                "required_skills": skills, "listed_skills": listed, "category": cat, "budget": budget,
                "country": str(r[m["country"]]) if m["country"] and pd.notna(r[m["country"]]) else None,
                "posted_at": str(r[m["posted"]])[:10] if m["posted"] and pd.notna(r[m["posted"]]) else None,
                "source": folder, "provenance": f"{REAL}:{folder}",
                "target_persona": persona_for_category(cat),
            })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-rows", type=int, default=60000)
    ap.add_argument("--synthetic-fallback", action="store_true",
                    help="if no raw data is present, generate clearly-labelled synthetic jobs")
    ap.add_argument("--report", action="store_true", help="print detected columns per CSV")
    a = ap.parse_args()

    jobs: list[dict] = []
    for folder in JOB_FOLDERS:
        if (RAW / folder).exists():
            got = load_folder(folder, a.max_rows, a.report)
            print(f"{folder}: kept {len(got)} jobs")
            jobs += got
    if not jobs:
        if not a.synthetic_fallback:
            print("No raw data found in data/raw/. Download first or pass --synthetic-fallback.", file=sys.stderr)
            return 1
        jobs = gen_jobs(400)
        print(f"WARNING: using {len(jobs)} SYNTHETIC jobs (provenance=synthetic). Not real data.")

    seen: set[str] = set()
    uniq = []
    for j in jobs:
        h = norm_hash(j["title"], j["description"])
        if h in seen:
            continue
        seen.add(h)
        uniq.append(j)
    n = write_jsonl(PROCESSED / "jobs.jsonl", uniq)
    print(f"wrote {n} unique jobs (dropped {len(jobs) - n} duplicates) -> data/processed/jobs.jsonl")
    return 0


if __name__ == "__main__":
    sys.exit(main())
