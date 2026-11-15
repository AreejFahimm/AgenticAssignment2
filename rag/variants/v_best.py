"""Candidate shipped pipeline: decomposition + hybrid + rerank (+ outcome). Flags exist for ablation."""
from rag.variants.pipeline import Config, run

CFG = Config("best", decompose=True, hybrid=True, rerank=True)


def retrieve(job: dict, index, k: int = 5, **_) -> list[dict]:
    return run(job, index, k, CFG)
