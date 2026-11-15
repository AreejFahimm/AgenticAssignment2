"""Micro-benchmark for the E5 optimisation: cost of the cross-encoder pool size (seconds per job).

    python -m evals.runners.latency_bench  ->  evals/results/latency_bench.json
"""
import json
import time

from evals.runners._harness import ROOT, dev
from rag.index.store import get_index
from rag.variants.pipeline import Config, run

ARMS = [("v0", Config("v0")), ("v2 hybrid", Config("v2", hybrid=True)), ("v3 rerank pool=20", Config("v3", hybrid=True, rerank=True, pool=20)),
        ("v3 rerank pool=10", Config("v3", hybrid=True, rerank=True, pool=10)),
        ("best pool=20", Config("best", decompose=True, hybrid=True, rerank=True, pool=20)),
        ("best pool=10", Config("best10", decompose=True, hybrid=True, rerank=True, pool=10, per_req=4))]


def main(n: int = 15) -> dict:
    out = {}
    for persona in ("fullstack_web_dev", "data_analyst"):
        idx = get_index(persona)
        rows = dev(persona)[:n]
        for name, cfg in ARMS:
            run(rows[0], idx, 5, cfg)  # warm-up
            ts = []
            for r in rows:
                t = time.time()
                run(r, idx, 5, cfg)
                ts.append(time.time() - t)
            out.setdefault(name, []).extend(ts)
    res = {k: dict(mean_s=round(sum(v) / len(v), 3), p95_s=round(sorted(v)[int(len(v) * .95)], 3), n=len(v)) for k, v in out.items()}
    (ROOT / "evals" / "results" / "latency_bench.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    return res


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
