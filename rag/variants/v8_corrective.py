"""V8 (agentic group): corrective RAG as a LangGraph loop: retrieve -> grade -> re-query (once) -> answer or REFUSE.

Grading is a cheap cosine check of each hit against the job post (no LLM), so it is fast and reproducible.
If nothing clears the threshold after the re-query the variant returns [] with refused=True, so the Writer
must not claim experience (R5) and the decision node can recommend a skip.
"""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from rag.index.store import embed_query
from rag.variants.common import job_text
from rag.variants.pipeline import Config, run

GRADE_THRESHOLD = 0.66   # min cosine(job post, evidence) to count as relevant; calibrated on DEV, checked on HELD-OUT: evals/results/v8_calibration.json (0.50 refused nothing)
MIN_RELEVANT = 1
FIRST = Config("v8_first", hybrid=True, rerank=True)
SECOND = Config("v8_requery", decompose=True, hybrid=True, rerank=True)


class S(TypedDict, total=False):
    job: dict
    index: object
    k: int
    hits: list[dict]
    attempt: int
    refused: bool


def _retrieve(s: S) -> S:
    cfg = FIRST if s.get("attempt", 0) == 0 else SECOND
    return {"hits": run(s["job"], s["index"], s["k"], cfg), "attempt": s.get("attempt", 0) + 1}


def _grade(s: S) -> S:
    idx, q = s["index"], embed_query(job_text(s["job"])[:1500])
    pos = {e["evidence_id"]: i for i, e in enumerate(idx.items)}
    kept = [dict(h, grade="relevant") for h in s["hits"] if float(idx.emb[pos[h["evidence_id"]]] @ q) >= GRADE_THRESHOLD]
    return {"hits": kept}


def _route(s: S) -> str:
    if len(s["hits"]) >= MIN_RELEVANT:
        return "done"
    return "requery" if s.get("attempt", 0) < 2 else "refuse"


def _refuse(s: S) -> S:
    return {"hits": [], "refused": True}


def _build():
    g = StateGraph(S)
    g.add_node("retrieve", _retrieve)
    g.add_node("grade", _grade)
    g.add_node("refuse", _refuse)
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "grade")
    g.add_conditional_edges("grade", _route, {"done": END, "requery": "retrieve", "refuse": "refuse"})
    g.add_edge("refuse", END)
    return g.compile()


_GRAPH = _build()


def run_full(job: dict, index, k: int = 5) -> dict:
    return _GRAPH.invoke({"job": job, "index": index, "k": k, "attempt": 0})


def retrieve(job: dict, index, k: int = 5, **_) -> list[dict]:
    return [dict(h, variant="v8_corrective") for h in run_full(job, index, k)["hits"]]
