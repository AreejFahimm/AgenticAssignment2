"""Shared evaluation harness: run jobs through the bid graph in-process against GigSim-local."""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

os.environ.setdefault("GIGSIM_INPROCESS", "1")
os.environ.setdefault("GIGSIM_ERROR_RATE", "0")
os.environ.setdefault("MCP_RATE_LIMIT", "1000000")   # per-user limiter is tested separately; evals issue bursts
os.environ.setdefault("GIGSIM_RATE_LIMIT", "1000000")
os.environ.setdefault("GIGSIM_START_CONNECTS", "1000000")   # evals run hundreds of submissions per arm
os.environ.setdefault("MEMORY_DB", ":memory:")
os.environ.setdefault("MODEL_PROFILE", "offline")

from langgraph.checkpoint.memory import MemorySaver  # noqa: E402
from langgraph.types import Command  # noqa: E402

from agent.graphs.bid_graph import build_bid_graph  # noqa: E402
from agent.nodes.scout import SeenStore  # noqa: E402
from agent.runtime import Runtime  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PERSONAS = ["ai_ml_engineer", "fullstack_web_dev", "data_analyst"]


def read_jsonl(p: Path) -> list[dict]:
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def dev(persona: str, kind: str = "dev") -> list[dict]:
    return read_jsonl(ROOT / "evals" / "datasets" / f"{kind}_{persona}.jsonl")


def public(job_id: str) -> dict:
    from gigsim_local.app import JOBS, public_job
    return public_job(JOBS[job_id])


class Harness:
    def __init__(self):
        self.rt = Runtime(seen=SeenStore(":memory:"))
        self.graph = build_bid_graph(MemorySaver())

    async def run(self, persona: str, job_id: str, *, user: str | None = None, approve: bool = False, weekly_budget: int = 10_000, strategy: str | None = None) -> dict:
        """Returns the final state + wall-clock timings. `approve=True` is the SIMULATED human used only by evals."""
        user = user or f"eval-{uuid.uuid4().hex[:6]}"
        tid = f"{user}.{job_id}"
        cfg = {"configurable": {"thread_id": tid, "rt": self.rt}}
        state = dict(user_id=user, persona=persona, thread_id=tid, trace_id=tid, job=public(job_id), steps=0, tokens=0, revisions=0,
                     settings=dict(weekly_connects_budget=weekly_budget, connects_spent_this_week=0), **({"strategy": strategy} if strategy else {}))
        t0 = time.time()
        out = await self.graph.ainvoke(state, cfg)
        t_analyse = time.time() - t0
        snap = await self.graph.aget_state(cfg)
        waiting = bool(snap.next)
        if waiting and approve:
            out = await self.graph.ainvoke(Command(resume={"status": "approved"}), cfg)
        return dict(state=out, waiting=waiting, seconds=time.time() - t0, seconds_to_draft=t_analyse, user=user)


def f1(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return dict(precision=round(p, 4), recall=round(r, 4), f1=round(2 * p * r / (p + r), 4) if p + r else 0.0)


def pct(xs: list[float], q: float) -> float:
    s = sorted(xs)
    return round(s[min(int(len(s) * q), len(s) - 1)], 3) if s else 0.0
