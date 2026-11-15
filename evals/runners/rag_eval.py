"""Retrieval evaluation (B4/B5): Recall@5, MRR, nDCG@10 per variant, persona and job type.

    python -m evals.runners.rag_eval [--per-persona 80]

Writes evals/results/rag_retrieval.json and rag_retrieval.csv. Gold = silver labels (see DATA_CARD).
Jobs with empty gold evidence are scored only for refusal behaviour (V8), not for recall.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import time
from collections import defaultdict
from pathlib import Path

from rag.index.store import get_index
from rag.retriever import get_retriever

ROOT = Path(__file__).resolve().parents[2]
PERSONAS = ["ai_ml_engineer", "fullstack_web_dev", "data_analyst"]
VARIANTS = ["v0", "v1", "v2", "v3", "v4", "v6", "v8", "best", "best_ctx", "ship"]


def recall_at(gold: set[str], ranked: list[str], k: int) -> float:
    return len(gold & set(ranked[:k])) / len(gold)


def mrr(gold: set[str], ranked: list[str]) -> float:
    for i, r in enumerate(ranked, 1):
        if r in gold:
            return 1.0 / i
    return 0.0


def ndcg(gold: set[str], ranked: list[str], k: int = 10) -> float:
    dcg = sum(1.0 / math.log2(i + 2) for i, r in enumerate(ranked[:k]) if r in gold)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(min(len(gold), k)))
    return dcg / idcg if idcg else 0.0


def load_dev(persona: str, n: int) -> list[dict]:
    p = ROOT / "evals" / "datasets" / f"dev_{persona}.jsonl"
    rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows[:n]


def job_type(job: dict) -> str:
    return "multi_req(>=3)" if len(job["required_skills"]) >= 3 else "few_req(<3)"


def main(per_persona: int, variants: list[str], merge: bool = False) -> None:
    acc: dict = defaultdict(lambda: defaultdict(list))
    lat: dict = defaultdict(list)
    refusal = defaultdict(lambda: [0, 0])  # variant -> [correct refusals, empty-gold jobs]
    for persona in PERSONAS:
        idx = get_index(persona)
        for job in load_dev(persona, per_persona):
            gold = set(job["gold"]["relevant_evidence"])
            print(".", end="", flush=True)
            for v in variants:
                fn = get_retriever(v)
                t = time.time()
                hits = fn(job, idx, 10)
                lat[v].append(time.time() - t)
                ranked = [h["evidence_id"] for h in hits]
                if not gold:
                    if v == "v8":
                        refusal[v][1] += 1
                        refusal[v][0] += int(not ranked)
                    continue
                m = dict(recall5=recall_at(gold, ranked, 5), mrr=mrr(gold, ranked), ndcg10=ndcg(gold, ranked, 10))
                for key in ("ALL", persona, job_type(job)):
                    for name, val in m.items():
                        acc[(v, key)][name].append(val)
        print(f"done {persona} ({time.strftime('%H:%M:%S')})", flush=True)
    rows = []
    for (v, key), ms in sorted(acc.items()):
        rows.append(dict(variant=v, slice=key, n=len(ms["recall5"]),
                         **{k: round(sum(x) / len(x), 4) for k, x in ms.items()}))
    lat_stats = {v: dict(p50=round(sorted(x)[len(x) // 2], 3), p95=round(sorted(x)[int(len(x) * 0.95)], 3)) for v, x in lat.items()}
    out = dict(rows=rows, latency_s=lat_stats, v8_refusal_on_empty_gold=dict(zip(("correct", "total"), refusal["v8"])),
               per_persona_jobs=per_persona, labels="silver (rule-derived), see docs/DATA_CARD.md")
    res = ROOT / "evals" / "results"
    res.mkdir(parents=True, exist_ok=True)
    old = res / "rag_retrieval.json"
    if merge and old.exists():  # keep rows/latency of variants that were not re-run
        prev = json.loads(old.read_text(encoding="utf-8"))
        rows = [r for r in prev["rows"] if r["variant"] not in variants] + rows
        lat_stats = {**{k: v for k, v in prev["latency_s"].items() if k not in variants}, **lat_stats}
        if "v8" not in variants:
            out["v8_refusal_on_empty_gold"] = prev["v8_refusal_on_empty_gold"]
        out["rows"], out["latency_s"] = rows, lat_stats
    (res / "rag_retrieval.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    with (res / "rag_retrieval.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{'variant':8} {'R@5':>6} {'MRR':>6} {'nDCG10':>7} {'p95(s)':>7}")
    for r in rows:
        if r["slice"] == "ALL":
            print(f"{r['variant']:8} {r['recall5']:6.3f} {r['mrr']:6.3f} {r['ndcg10']:7.3f} {lat_stats[r['variant']]['p95']:7.2f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-persona", type=int, default=80)
    ap.add_argument("--variants", nargs="*", default=VARIANTS)
    ap.add_argument("--merge", action="store_true", help="keep results of variants not re-run")
    a = ap.parse_args()
    main(a.per_persona, a.variants, a.merge)
