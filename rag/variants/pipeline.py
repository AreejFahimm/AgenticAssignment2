"""Composable retrieval pipeline: decompose? -> (dense | hybrid) -> outcome boost? -> rerank?

Every named variant (v0..v4, best) is a thin configuration of this, so ablations are one flag each.
"""
from __future__ import annotations

from dataclasses import dataclass

from rag.index.store import reranker
from rag.variants.common import EVIDENCE_TYPES, job_text, requirements_of, rrf, to_hits


@dataclass(frozen=True)
class Config:
    name: str
    decompose: bool = False
    hybrid: bool = False
    rerank: bool = False
    outcome: bool = False
    pool: int = 20          # candidates fed to the reranker / taken per query
    per_req: int = 6        # hits per requirement when decomposing
    outcome_weight: float = 0.02
    contextual: bool = False   # V6: index with a prepended context line


def _candidates(job: dict, index, cfg: Config) -> dict[int, float]:
    queries = requirements_of(job) if cfg.decompose else [job_text(job)]
    rankings = []
    n = cfg.per_req if cfg.decompose else cfg.pool
    for q in queries:
        rankings.append([i for i, _ in index.dense(q, n, EVIDENCE_TYPES)])
        if cfg.hybrid:
            rankings.append([i for i, _ in index.bm25_search(q, n, EVIDENCE_TYPES)])
    return rrf(rankings)


def run(job: dict, index, k: int, cfg: Config) -> list[dict]:
    if cfg.contextual and not getattr(index, "contextual", False):
        from rag.index.store import get_index
        index = get_index(index.persona, True)
    fused = _candidates(job, index, cfg)
    if cfg.outcome:  # V4: boost evidence from projects whose proposals won / got replies
        for i in fused:
            fused[i] += cfg.outcome_weight * index.outcome_by_project.get(index.items[i].get("project_id"), 0.0)
    ranked = sorted(fused.items(), key=lambda t: -t[1])
    if cfg.rerank:  # V3: cross-encoder over the pool, scored against the whole job post
        pool = ranked[: cfg.pool]
        if pool:
            scores = list(reranker().rerank(job_text(job), [index.items[i]["text"] for i, _ in pool]))
            ranked = sorted(((i, float(s)) for (i, _), s in zip(pool, scores)), key=lambda t: -t[1])
    return to_hits(index, ranked, k, cfg.name)
