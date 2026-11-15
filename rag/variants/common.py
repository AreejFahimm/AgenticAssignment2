"""Shared helpers for retrieval variants. Interface: retrieve(job, index, k=5, **kw) -> list[evidence dict + score]."""
from __future__ import annotations

import re

EVIDENCE_TYPES = {"case_study", "repo_readme", "code", "review"}  # past_proposal is NOT evidence of experience


def job_text(job: dict) -> str:
    return f"{job.get('title', '')}. {job.get('description', '')}".strip()


def requirements_of(job: dict) -> list[str]:
    """Heuristic requirement decomposition (the graph's Job Analyst supplies job['requirements'] when available)."""
    if job.get("requirements"):
        return list(job["requirements"])
    reqs = [f"experience with {s}" for s in job.get("required_skills", [])]
    for sent in re.split(r"(?<=[.!?])\s+", job.get("description", "")):
        sent = sent.strip()
        if 25 <= len(sent) <= 220:
            reqs.append(sent)
    return reqs[:8] or [job_text(job)]


def rrf(rankings: list[list[int]], k: int = 60) -> dict[int, float]:
    scores: dict[int, float] = {}
    for ranking in rankings:
        for r, i in enumerate(ranking):
            scores[i] = scores.get(i, 0.0) + 1.0 / (k + r + 1)
    return scores


def to_hits(index, scored: list[tuple[int, float]], k: int, variant: str) -> list[dict]:
    out = []
    for i, s in scored[:k]:
        e = dict(index.items[i])
        e["score"] = float(s)
        e["variant"] = variant
        out.append(e)
    return out
