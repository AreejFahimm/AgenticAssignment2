"""Run ONE job through the bid graph (first end-to-end path). Pauses at the approval interrupt, then resumes.

  python scripts/run_job.py [--persona ai_ml_engineer] [--index 0] [--approve|--reject|--edit]
"""
import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("GIGSIM_INPROCESS", "1")
os.environ.setdefault("GIGSIM_ERROR_RATE", "0")
os.environ.setdefault("MEMORY_DB", ":memory:")

from langgraph.checkpoint.memory import MemorySaver  # noqa: E402
from langgraph.types import Command  # noqa: E402

from agent.graphs.bid_graph import build_bid_graph  # noqa: E402
from agent.nodes.scout import SeenStore  # noqa: E402
from agent.runtime import Runtime  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


async def main(a):
    rows = [json.loads(line) for line in (ROOT / "evals/datasets" / f"dev_{a.persona}.jsonl").read_text(encoding="utf-8").splitlines()]
    job = next(r for i, r in enumerate(rows) if i >= a.index and r["gold"]["decision"] == "bid")
    job.pop("gold")
    from gigsim_local.app import JOBS, public_job
    job = public_job(JOBS[job["job_id"]]) | {"target_persona": job.get("target_persona")}
    rt = Runtime(seen=SeenStore(":memory:"))
    g = build_bid_graph(MemorySaver())
    tid = f"demo-{uuid.uuid4().hex[:6]}"
    cfg = {"configurable": {"thread_id": tid, "rt": rt}}
    init = dict(user_id="demo-user", persona=a.persona, thread_id=tid, trace_id=tid, job=job, steps=0, tokens=0, revisions=0,
                settings=dict(weekly_connects_budget=60, connects_spent_this_week=0))
    out = await g.ainvoke(init, cfg)
    print("JOB:", job["title"], "| status:", out["status"], "| decision:", out["decision"]["action"], out["decision"]["reasons"])
    print("ERRORS:", out.get("errors"))
    print("DRAFT:", out.get("proposal_draft", {}).get("cover_letter"))
    print("VERIF:", out.get("claim_verification"))
    for step in out["trace"]:
        print("  trace:", step)
    snap = await g.aget_state(cfg)
    if snap.next:
        payload = snap.tasks[0].interrupts[0].value
        print("\n--- APPROVAL REQUIRED ---")
        print("final_text:", payload["final_text"])
        print("dry_run:", payload["dry_run_preview"]["connects_cost"], "connects; balance after", payload["dry_run_preview"]["balance_after"])
        resume = {"status": "approved"}
        if a.reject:
            resume = {"status": "rejected", "reason": "demo"}
        if a.edit:
            resume = {"status": "edited", "edited_text": payload["final_text"].split(". ", 1)[1]}
        out = await g.ainvoke(Command(resume=resume), cfg)
        print("after resume -> status:", out["status"], "| submission:", out.get("submission"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", default="ai_ml_engineer")
    ap.add_argument("--index", type=int, default=0)
    ap.add_argument("--reject", action="store_true")
    ap.add_argument("--edit", action="store_true")
    asyncio.run(main(ap.parse_args()))
