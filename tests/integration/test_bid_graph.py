"""Integration tests for the bid graph against GigSim-local (in-process): parallelism, interrupts, loops, durability."""
import json
import os
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ["GIGSIM_INPROCESS"] = "1"
os.environ["GIGSIM_ERROR_RATE"] = "0"
os.environ["MEMORY_DB"] = ":memory:"
os.environ["MODEL_PROFILE"] = "offline"

from langgraph.checkpoint.memory import MemorySaver  # noqa: E402
from langgraph.types import Command  # noqa: E402

from agent.checkpoint import make_checkpointer  # noqa: E402
from agent.graphs.bid_graph import build_bid_graph  # noqa: E402
from agent.memory.promotion_rules import record_edit, should_promote_style, style_rules  # noqa: E402
from agent.nodes.scout import SeenStore  # noqa: E402
from agent.runtime import Runtime  # noqa: E402
from gigsim_local.app import BALANCES, JOBS, public_job  # noqa: E402

pytestmark = pytest.mark.skipif(not (ROOT / "evals/datasets/dev_fullstack_web_dev.jsonl").exists(), reason="run data pipeline first")
PERSONA = "fullstack_web_dev"


def dev_rows(persona=PERSONA):
    return [json.loads(line) for line in (ROOT / "evals/datasets" / f"dev_{persona}.jsonl").read_text(encoding="utf-8").splitlines()]


def job_of(row):
    return public_job(JOBS[row["job_id"]]) | {"target_persona": row.get("target_persona")}


def init(job, user=None, **kw):
    tid = f"t-{uuid.uuid4().hex[:8]}"
    user = user or f"user-{uuid.uuid4().hex[:6]}"
    return tid, user, dict(user_id=user, persona=PERSONA, thread_id=tid, trace_id=tid, job=job, steps=0, tokens=0, revisions=0,
                           settings=dict(weekly_connects_budget=100, connects_spent_this_week=0), **kw)


def cfg(tid, rt):
    return {"configurable": {"thread_id": tid, "rt": rt}}


async def run_until_approval(g, rt):
    for row in [r for r in dev_rows() if r["gold"]["decision"] == "bid"][:30]:
        tid, user, state = init(job_of(row))
        out = await g.ainvoke(state, cfg(tid, rt))
        if out["status"] == "waiting_approval":
            return tid, user, out
    pytest.skip("no job reached approval")


async def test_parallel_branches_interrupt_and_approve():
    rt = Runtime(seen=SeenStore(":memory:"))
    g = build_bid_graph(MemorySaver())
    tid, user, out = await run_until_approval(g, rt)
    nodes = [t["node"] for t in out["trace"]]
    assert {"analyst", "risk_assessor", "fit_matcher"} <= set(nodes)               # parallel branches ran
    assert nodes.index("decide") > max(nodes.index(n) for n in ("analyst", "risk_assessor", "fit_matcher"))  # join before decide
    assert "submit" not in nodes and "submission" not in out                        # nothing sent before approval
    snap = await g.aget_state(cfg(tid, rt))
    payload = snap.tasks[0].interrupts[0].value
    for k in ("draft", "evidence", "claim_verification", "risk_report", "price_quote", "dry_run_preview", "compliance"):
        assert k in payload                                                          # C5 payload
    bal0 = BALANCES[f"user-{user}-token"]
    res = await g.ainvoke(Command(resume={"status": "approved"}), cfg(tid, rt))
    assert res["status"] == "submitted" and BALANCES[f"user-{user}-token"] == bal0 - payload["dry_run_preview"]["connects_cost"]
    assert "[" not in payload["final_text"]                                         # evidence markers stripped from what is sent


async def test_reject_with_reason_sends_nothing():
    rt = Runtime(seen=SeenStore(":memory:"))
    g = build_bid_graph(MemorySaver())
    tid, user, _ = await run_until_approval(g, rt)
    bal0 = BALANCES[f"user-{user}-token"]
    res = await g.ainvoke(Command(resume={"status": "rejected", "reason": "too generic"}), cfg(tid, rt))
    assert res["status"] == "rejected" and "submission" not in res and BALANCES[f"user-{user}-token"] == bal0


async def test_edit_is_rechecked_by_compliance_and_blocked_edit_asks_again():
    rt = Runtime(seen=SeenStore(":memory:"))
    g = build_bid_graph(MemorySaver())
    tid, user, _ = await run_until_approval(g, rt)
    res = await g.ainvoke(Command(resume={"status": "edited", "edited_text": "x"}), cfg(tid, rt))  # too short -> blocked
    assert res["status"] == "waiting_approval" and "blocked by compliance" in res["approval_error"]
    snap = await g.aget_state(cfg(tid, rt))
    assert snap.next  # still paused, not submitted
    res = await g.ainvoke(Command(resume={"status": "edited", "edited_text": "Hello, I would like to help. Call me on WhatsApp +1 555 123 4567 or mail me@x.com. "
                                                                                 "I can deliver a first milestone and share progress before we go further with scope, timeline and acceptance criteria."}), cfg(tid, rt))
    assert res["status"] == "submitted"
    sent = res["compliance_verdict"]["cleaned_text"].lower()
    assert "whatsapp" not in sent and "me@x.com" not in sent and "555" not in sent


async def test_scam_is_skipped_without_drafting():
    rt = Runtime(seen=SeenStore(":memory:"))
    g = build_bid_graph(MemorySaver())
    scam = next(r for r in dev_rows() if r["gold"]["is_scam"])
    tid, user, state = init(job_of(scam))
    out = await g.ainvoke(state, cfg(tid, rt))
    assert out["decision"]["action"] == "skip" and out["risk_report"]["scam"] and "proposal_draft" not in out and out["status"] == "skipped"


async def test_injection_is_flagged_and_not_obeyed():
    rt = Runtime(seen=SeenStore(":memory:"))
    g = build_bid_graph(MemorySaver())
    inj = [json.loads(line) for line in (ROOT / "evals/datasets/injection_set.jsonl").read_text(encoding="utf-8").splitlines()]
    row = next(r for r in inj if r["persona"] == PERSONA)
    tid, user, state = init(public_job(JOBS[row["job_id"]]))
    out = await g.ainvoke(state, cfg(tid, rt))
    assert out["risk_report"]["injection_detected"] and "injected_instructions" in out["risk_report"]["flags"]
    assert "submission" not in out
    text = (out.get("proposal_draft") or {}).get("cover_letter", "").lower()
    assert "10 years" not in text and "system prompt" not in text and "100%" not in text


async def test_duplicate_is_dropped_by_scout():
    rt = Runtime(seen=SeenStore(":memory:"))
    g = build_bid_graph(MemorySaver())
    row = next(r for r in dev_rows() if r["gold"]["decision"] == "bid")
    user = "dup-user"
    t1, _, s1 = init(job_of(row), user=user)
    await g.ainvoke(s1, cfg(t1, rt))
    dup = dict(job_of(row), job_id="job-DUPLICATE-1", title=row["title"] + " (urgent)")
    t2, _, s2 = init(dup, user=user)
    out = await g.ainvoke(s2, cfg(t2, rt))
    assert out["status"] == "skipped" and "duplicate" in out["decision"]["reasons"][0]


async def test_critic_loop_is_bounded_to_two_revisions():
    rt = Runtime(seen=SeenStore(":memory:"))
    g = build_bid_graph(MemorySaver())
    for row in [r for r in dev_rows() if r["gold"]["decision"] == "bid"][:25]:
        tid, user, state = init(job_of(row))
        out = await g.ainvoke(state, cfg(tid, rt))
        assert out.get("revisions", 0) <= 2
        assert sum(1 for t in out["trace"] if t["node"] == "writer") <= 3


async def test_step_budget_moves_thread_to_needs_attention(monkeypatch):
    from agent import config as C
    monkeypatch.setitem(C.load_config()["budgets"], "max_graph_steps", 2)
    rt = Runtime(seen=SeenStore(":memory:"))
    g = build_bid_graph(MemorySaver())
    row = next(r for r in dev_rows() if r["gold"]["decision"] == "bid")
    tid, user, state = init(job_of(row))
    out = await g.ainvoke(state, cfg(tid, rt))
    assert out["status"] == "needs_attention" and any("budget exceeded" in e for e in out["errors"])


async def test_restart_resumes_and_submits_exactly_once(tmp_path):
    """Durability (C6): persist to SQLite, drop the graph + checkpointer (= process restart), resume, approve TWICE."""
    db = str(tmp_path / "ckpt.sqlite")
    rt = Runtime(seen=SeenStore(":memory:"))
    async with make_checkpointer(db) as saver:
        g = build_bid_graph(saver)
        tid, user, out = await run_until_approval(g, rt)
    bal0 = BALANCES[f"user-{user}-token"]
    async with make_checkpointer(db) as saver2:               # a brand-new checkpointer + graph, like after a crash
        g2 = build_bid_graph(saver2)
        snap = await g2.aget_state(cfg(tid, rt))
        assert snap.next == ("approval",)                      # pending approval survived the restart
        r1 = await g2.ainvoke(Command(resume={"status": "approved"}), cfg(tid, rt))
        assert r1["status"] == "submitted"
        cost = r1["submission"]["connects_cost"]
        again = await g2.ainvoke(Command(resume={"status": "approved"}), cfg(tid, rt))  # double click / replay
        assert again["submission"]["proposal_id"] == r1["submission"]["proposal_id"]
    assert BALANCES[f"user-{user}-token"] == bal0 - cost                       # Connects spent exactly once


async def test_replay_from_checkpoint_history():
    rt = Runtime(seen=SeenStore(":memory:"))
    g = build_bid_graph(MemorySaver())
    tid, user, out = await run_until_approval(g, rt)
    history = [s async for s in g.aget_state_history(cfg(tid, rt))]
    assert len(history) > 5                                    # every superstep is a checkpoint we can replay from
    before_writer = next(s for s in history if s.next == ("writer",))
    replay = await g.ainvoke(None, before_writer.config | {"configurable": {**before_writer.config["configurable"], "rt": rt}})
    assert replay["proposal_draft"]["cover_letter"]


def test_style_memory_promotion_rule():
    from agent.memory.store import get_store
    get_store()
    user = f"style-{uuid.uuid4().hex[:5]}"
    orig = "I am passionate about data. I built a dashboard for retail. I can start now."
    edited = "I built a dashboard for retail. I can start now."
    r1 = record_edit(user, "job-A", orig, edited)
    assert "cut_first_sentence" in r1["observed"] and not r1["promoted"] and style_rules(user) == []   # one edit is NOT enough
    record_edit(user, "job-A", orig, edited)                                                            # same job again: still not enough
    assert style_rules(user) == []
    r3 = record_edit(user, "job-B", orig, edited)
    assert "cut_first_sentence" in r3["promoted"] and "cut_first_sentence" in style_rules(user)         # 2 distinct jobs -> promoted
    assert should_promote_style(2, 2) and not should_promote_style(5, 1)
