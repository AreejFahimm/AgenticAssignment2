"""Job Analyst: extract a structured JobSpec. No tools. Input is neutralised + delimited (injection defence)."""
from __future__ import annotations

import re
import time

from agent import llm
from agent.handoffs import JobSpec
from agent.runtime import tr
from agent.security import neutralise, wrap_untrusted
from rag.variants.common import requirements_of

_DELIV = re.compile(r"\b(build|create|develop|deliver|design|fix|implement|set up|migrate|automate|analy[sz]e|clean|train|deploy)\b", re.I)


def heuristic_spec(job: dict, safe_desc: str) -> JobSpec:
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", safe_desc) if s.strip()]
    b = job.get("budget", {})
    days = re.search(r"(\d+)\s*(?:day|week)s?", safe_desc, re.I)
    return JobSpec(
        job_id=job["job_id"], title=job["title"],
        deliverables=[s for s in sents if _DELIV.search(s)][:5],
        required_skills=job.get("required_skills", []),
        requirements=requirements_of(dict(job, description=safe_desc)),
        budget_type=b.get("type", "unknown") if b.get("type") in ("fixed", "hourly") else "unknown",
        budget_min=b.get("min"), budget_max=b.get("max"),
        timeline_days=int(days.group(1)) * (7 if "week" in days.group(0).lower() else 1) if days else None,
        screening_questions=[s for s in sents if s.endswith("?")][:5],
        hidden_needs=[], category=job.get("category"))


async def analyst(state, config):
    t = time.time()
    job = state["job"]
    safe = neutralise(job.get("description", ""))
    spec = heuristic_spec(job, safe)
    if llm.enabled("analyst"):
        try:
            d = llm.complete_json("analyst", wrap_untrusted(f"{job['title']}\n{safe}", "job_post"))
            spec = JobSpec(**{**spec.model_dump(), **{k: v for k, v in d.items() if k in JobSpec.model_fields and v}})
        except Exception as e:  # noqa: BLE001  fall back to heuristics, keep going
            return dict(job_spec=spec.model_dump(), steps=1, errors=[f"analyst llm failed: {e}"], trace=[tr("analyst", t, fallback=True)])
    return dict(job_spec=spec.model_dump(), steps=1, trace=[tr("analyst", t, requirements=len(spec.requirements))])
