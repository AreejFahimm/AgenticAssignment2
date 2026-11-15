"""Fit Matcher: map every requirement to portfolio evidence (via the Portfolio MCP server) and score the fit."""
from __future__ import annotations

import re
import time

from agent.config import load_config
from agent.handoffs import FitReport, RequirementMatch
from agent.runtime import rt_of, tr
from agent.security import neutralise
from rag.variants.common import requirements_of

_STOP = set("a an the and or of to in on for with by from at as is are was be we our you your i it this that experience using use need needed looking".split())


def _tok(t: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9\+\#\.]+", t.lower()) if w not in _STOP and len(w) > 2}


def strength(requirement: str, ev: dict) -> float:
    """Evidence strength for a requirement: lexical overlap with text + skills metadata (0..1)."""
    r = _tok(requirement)
    if not r:
        return 0.0
    ev_tok = _tok(ev["text"]) | _tok(" ".join(ev.get("skills", [])))
    return min(1.0, len(r & ev_tok) / len(r) + (0.25 if any(s.lower() in requirement.lower() for s in ev.get("skills", [])) else 0.0))


async def fit_matcher(state, config):
    t, rt = time.time(), rt_of(config)
    # Runs IN PARALLEL with the Analyst, so it derives requirements from the (sanitised) job itself, not from job_spec.
    job = state["job"]
    spec = dict(title=job["title"], required_skills=job.get("required_skills", []),
                requirements=requirements_of(dict(job, description=neutralise(job.get("description", "")))))
    k = load_config()["rag"]["k"]
    matrix, evidence, seen = [], [], set()
    reqs = (spec["requirements"] or [spec["title"]])[:6]
    for req in reqs:
        res = await rt.hub.call("fit_matcher", "portfolio.search_evidence", {"requirement": req, "k": min(k, 3)},
                                user=state["user_id"], persona=state["persona"], trace_id=state.get("trace_id", ""))
        items = res["items"]
        scored = sorted(((strength(req, i), i) for i in items), key=lambda x: -x[0])
        good = [(s, i) for s, i in scored if s >= 0.34]
        matrix.append(RequirementMatch(requirement=req, evidence_ids=[i["evidence_id"] for _, i in good[:2]],
                                       strength=round(good[0][0], 3) if good else 0.0))
        for _, i in good[:2]:
            if i["evidence_id"] not in seen:
                seen.add(i["evidence_id"])
                evidence.append(i)
    score = sum(m.strength for m in matrix) / max(len(matrix), 1)
    skills = set(spec["required_skills"])
    ev_skills = {s.lower() for e in evidence for s in e.get("skills", [])}
    matched = sorted(s for s in skills if s.lower() in ev_skills)
    rep = FitReport(score=round(min(score, 1.0), 3), matched_skills=matched, missing_skills=sorted(skills - set(matched)),
                    evidence_ids=[e["evidence_id"] for e in evidence], matrix=matrix, refused=not evidence,
                    reasons=[f"{sum(1 for m in matrix if m.strength > 0)}/{len(matrix)} requirements have evidence"])
    return dict(fit_report=rep.model_dump(), evidence=evidence, steps=1, trace=[tr("fit_matcher", t, score=rep.score, evidence=len(evidence))])
