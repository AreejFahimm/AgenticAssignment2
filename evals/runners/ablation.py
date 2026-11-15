"""Ablate the best retrieval pipeline ONE component at a time (B5) and break results down by persona and job type.

    python -m evals.runners.ablation [--per-persona 60]  ->  evals/results/ablation.json

Hypothesis (written BEFORE running; see docs/DATA_CARD.md / report section 4):
  H1: requirement decomposition + hybrid + rerank raises evidence Recall@5 over V0 by >= 10 points on jobs with >= 3 requirements.
  H2: removing the reranker costs the most; removing decomposition costs little on jobs with < 3 requirements.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import replace

from evals.runners.rag_eval import PERSONAS, load_dev, job_type, mrr, ndcg, recall_at
from rag.index.store import get_index
from rag.variants.pipeline import Config, run
from evals.runners._harness import ROOT

BEST = Config("best", decompose=True, hybrid=True, rerank=True)
ARMS = {
    "V0 baseline": Config("v0"),
    "best (decompose+hybrid+rerank)": BEST,
    "best - decompose": replace(BEST, name="no_decompose", decompose=False),
    "best - hybrid": replace(BEST, name="no_hybrid", hybrid=False),
    "best - rerank": replace(BEST, name="no_rerank", rerank=False),
    "best + outcome boost": replace(BEST, name="plus_outcome", outcome=True),
    "best + contextual indexing (V6)": replace(BEST, name="best_ctx", contextual=True),
    "decompose+hybrid, no rerank": replace(BEST, name="dh_norerank", rerank=False),
    "decompose+hybrid+contextual, no rerank": replace(BEST, name="dhc_norerank", rerank=False, contextual=True),
    "contextual dense only (V6 dense)": Config("v6d", contextual=True),
    "hybrid+contextual, no rerank": Config("hc", hybrid=True, contextual=True),
    "best, rerank pool 10 (latency opt.)": replace(BEST, name="pool10", pool=10, per_req=4),
}


def main(per_persona: int) -> dict:
    acc: dict = {}
    for persona in PERSONAS:
        idx = get_index(persona)
        for job in load_dev(persona, per_persona):
            gold = set(job["gold"]["relevant_evidence"])
            if not gold:
                continue
            for name, cfg in ARMS.items():
                ranked = [h["evidence_id"] for h in run(job, idx, 10, cfg)]
                for sl in ("ALL", persona, job_type(job)):
                    d = acc.setdefault((name, sl), dict(r5=[], mrr=[], ndcg=[]))
                    d["r5"].append(recall_at(gold, ranked, 5))
                    d["mrr"].append(mrr(gold, ranked))
                    d["ndcg"].append(ndcg(gold, ranked))
        print("done", persona, flush=True)
    rows = [dict(arm=a, slice=s, n=len(v["r5"]), recall5=round(sum(v["r5"]) / len(v["r5"]), 4), mrr=round(sum(v["mrr"]) / len(v["mrr"]), 4),
                 ndcg10=round(sum(v["ndcg"]) / len(v["ndcg"]), 4)) for (a, s), v in sorted(acc.items())]
    return dict(rows=rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-persona", type=int, default=60)
    a = ap.parse_args()
    out = main(a.per_persona)
    (ROOT / "evals" / "results" / "ablation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    for r in out["rows"]:
        if r["slice"] == "ALL":
            print(f"{r['arm']:36} R@5={r['recall5']:.3f} MRR={r['mrr']:.3f} nDCG={r['ndcg10']:.3f} n={r['n']}")
