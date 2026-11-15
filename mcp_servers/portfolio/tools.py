"""Portfolio MCP tool implementations (read-only). Pure functions so they are unit-testable without MCP."""
from __future__ import annotations

import json
import os
from collections import Counter

from pydantic import BaseModel, Field

from agent.config import load_config

from rag.ingest.common_paths import PERSONAS_DIR
from rag.ingest.loaders import load_proposals
from rag.index.store import get_index
from rag.retriever import get_retriever


class EvidenceItem(BaseModel):
    evidence_id: str
    type: str = Field(description="case_study | repo_readme | code | review")
    source: str = Field(description="project id or file the item comes from")
    date: str | None = None
    outcome: str | None = None
    skills: list[str] = Field(default_factory=list)
    industry: str | None = None
    text: str
    score: float


class SearchResult(BaseModel):
    requirement: str
    variant: str
    items: list[EvidenceItem]


class CaseStudy(BaseModel):
    id: str
    markdown: str


class SkillList(BaseModel):
    skills: list[dict]


VARIANT = os.getenv("RAG_VARIANT") or load_config()["rag"]["variant"]  # shipped variant, chosen by evaluation (agent/config.yaml rag.variant)


def search_evidence(persona: str, requirement: str, k: int = 5, filters: dict | None = None,
                    variant: str | None = None) -> SearchResult:
    idx = get_index(persona)
    v = variant or VARIANT
    hits = get_retriever(v)({"title": requirement, "description": "", "required_skills": [], "requirements": [requirement]}, idx, k * 3)
    f = filters or {}
    out = []
    for h in hits:
        if f.get("type") and h["type"] != f["type"]:
            continue
        if f.get("skill") and f["skill"].lower() not in [s.lower() for s in h.get("skills", [])]:
            continue
        if f.get("industry") and h.get("industry") != f["industry"]:
            continue
        out.append(EvidenceItem(evidence_id=h["evidence_id"], type=h["type"], source=h.get("project_id") or h["evidence_id"],
                                date=h.get("date"), outcome=h.get("outcome"), skills=h.get("skills", []),
                                industry=h.get("industry"), text=h["text"], score=h["score"]))
        if len(out) >= k:
            break
    return SearchResult(requirement=requirement, variant=v, items=out)


def get_case_study(persona: str, case_id: str) -> CaseStudy:
    p = PERSONAS_DIR / persona / "case_studies" / f"{case_id}.md"
    if not p.exists() or "/" in case_id or "\\" in case_id or ".." in case_id:
        raise ValueError(f"unknown case study {case_id!r}")
    return CaseStudy(id=case_id, markdown=p.read_text(encoding="utf-8"))


def list_skills(persona: str) -> SkillList:
    c: Counter = Counter()
    for e in get_index(persona).items:
        c.update(e.get("skills", []))
    return SkillList(skills=[{"skill": s, "evidence_count": n} for s, n in c.most_common()])


def get_proposal(persona: str, proposal_id: str) -> dict:
    for p in load_proposals(persona):
        if p["proposal_id"] == proposal_id:
            return p
    raise ValueError(f"unknown proposal {proposal_id!r}")


def profile(persona: str) -> dict:
    return json.loads((PERSONAS_DIR / persona / "profile.json").read_text(encoding="utf-8"))
