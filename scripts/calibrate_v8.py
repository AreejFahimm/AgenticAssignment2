"""Calibrate V8's grading threshold on DEV jobs, then report refusal accuracy on the HELD-OUT split (never tuned on)."""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rag.index.store import embed_query, get_index  # noqa: E402
from rag.variants.common import job_text  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def best_cos(job, idx):
    q = embed_query(job_text(job)[:1500])
    types = {"case_study", "repo_readme", "code", "review"}
    m = [i for i, e in enumerate(idx.items) if e["type"] in types]
    return float(max(idx.emb[i] @ q for i in m))


def load(kind):
    out = []
    for p in ("ai_ml_engineer", "fullstack_web_dev", "data_analyst"):
        idx = get_index(p)
        for line in (ROOT / "evals/datasets" / f"{kind}_{p}.jsonl").read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            out.append((best_cos(r, idx), bool(r["gold"]["relevant_evidence"])))
    return out


def f1_at(th, rows):
    # positive class = "should refuse" (no gold evidence); predict refuse when best cosine < th
    tp = sum(1 for c, has in rows if c < th and not has)
    fp = sum(1 for c, has in rows if c < th and has)
    fn = sum(1 for c, has in rows if c >= th and not has)
    p = tp / (tp + fp) if tp + fp else 0
    r = tp / (tp + fn) if tp + fn else 0
    return 2 * p * r / (p + r) if p + r else 0, p, r


dev, held = load("dev"), load("heldout")
print("dev n", len(dev), "empty-gold", sum(1 for _, h in dev if not h))
cands = np.arange(0.40, 0.80, 0.01)
best = max(cands, key=lambda t: f1_at(t, dev)[0])
res = dict(threshold=round(float(best), 2), dev=dict(zip(("f1", "precision", "recall"), map(lambda x: round(x, 3), f1_at(best, dev)))),
           heldout=dict(zip(("f1", "precision", "recall"), map(lambda x: round(x, 3), f1_at(best, held)))),
           n_dev=len(dev), n_heldout=len(held), empty_gold_dev=sum(1 for _, h in dev if not h), empty_gold_heldout=sum(1 for _, h in held if not h),
           default_threshold_0_50=dict(zip(("f1", "precision", "recall"), map(lambda x: round(x, 3), f1_at(0.50, held)))))
print(json.dumps(res, indent=2))
(ROOT / "evals/results/v8_calibration.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
