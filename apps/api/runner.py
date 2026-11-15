"""Run manager: executes LangGraph threads in the background, records streamed events, resumes approvals, and
recovers after a restart. Used by the API and by the worker (scheduled scouting).

Idempotency: thread id = "<user>:<job_id>" so re-scanning / worker restarts never analyse or submit a job twice.
Degraded mode: if the marketplace is down the run ends `degraded`, is queued, and the health loop re-drives it
automatically when the marketplace answers again.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

from langgraph.types import Command

from agent import llm
from agent.graphs.bid_graph import build_bid_graph
from agent.graphs.conversation_graph import build_conversation_graph
from agent.mcp_client import MarketplaceDown, MCPHub
from agent.nodes.scout import SeenStore
from agent.runtime import Runtime
from agent.tracing import callbacks, write_trace
from apps.api import db

LIVE_STATUSES = {"running", "queued"}


class Runner:
    def __init__(self, checkpointer, hub: MCPHub | None = None, concurrency: int = 2):
        self.hub = hub or MCPHub()
        self.rt = Runtime(hub=self.hub, seen=SeenStore())
        self.bid = build_bid_graph(checkpointer)
        self.conv = build_conversation_graph(checkpointer)
        self.sem = asyncio.Semaphore(concurrency)           # polite concurrency toward the marketplace
        self.tasks: set[asyncio.Task] = set()
        self.marketplace_ok = True
        self.marketplace_error: str | None = None
        self._policy: tuple[float, dict] | None = None
        self._health_task: asyncio.Task | None = None
        self.pending_scans: set[str] = set()                # users whose scan failed during an outage (queued work)

    # ---------------- helpers ----------------
    async def platform_policy(self) -> dict:
        if self._policy and time.time() - self._policy[0] < 60:
            return self._policy[1]
        try:
            pol = (await self.hub.call("system", "marketplace.get_platform_policy", {}))["policy"]
            self._policy = (time.time(), pol)
            return pol
        except Exception:  # noqa: BLE001  policy unknown -> config-only rules apply
            return {}

    async def cfg(self, tid: str) -> dict:
        return {"configurable": {"thread_id": tid, "rt": self.rt, "platform_policy": await self.platform_policy()}, "callbacks": callbacks()}

    def _spawn(self, coro) -> asyncio.Task:
        t = asyncio.create_task(coro)
        self.tasks.add(t)
        t.add_done_callback(self.tasks.discard)
        return t

    async def wait_idle(self) -> None:
        while self.tasks:
            await asyncio.gather(*list(self.tasks), return_exceptions=True)

    # ---------------- bid threads ----------------
    async def start_bid(self, user: dict, job_id: str, *, force_new: bool = False) -> str:
        tid = f"{user['id']}.{job_id}"
        existing = db.q1("select status from runs where thread_id=?", tid)
        if existing and not force_new:
            return tid                                         # idempotent: never re-analyse
        if existing and force_new:
            tid = f"{tid}-r{uuid.uuid4().hex[:4]}"
        s = user["settings"]
        init = dict(user_id=user["id"], persona=user["persona"], thread_id=tid, trace_id=uuid.uuid4().hex[:12], job_id=job_id, steps=0,
                    tokens=0, revisions=0, autonomy=s.get("autonomy", "suggest"),
                    settings=dict(weekly_connects_budget=s.get("weekly_connects_budget"), connects_spent_this_week=s.get("connects_spent_this_week", 0)))
        db.run("insert into runs(thread_id,user_id,kind,job_id,title,status,created,updated) values(?,?,?,?,?,?,?,?)",
               tid, user["id"], "bid", job_id, job_id, "queued", time.time(), time.time())
        self._spawn(self._drive(self.bid, tid, user["id"], init, "bid"))
        return tid

    async def resume(self, user_id: str, tid: str, decision: dict) -> None:
        run = db.q1("select * from runs where thread_id=? and user_id=?", tid, user_id)
        if not run:
            raise KeyError("unknown thread")
        if run["status"] != "waiting_approval":
            raise ValueError(f"thread is {run['status']}, not waiting for approval")   # double-click safe
        graph = self.bid if run["kind"] == "bid" else self.conv
        db.run("update runs set status='running', updated=? where thread_id=?", time.time(), tid)
        self._spawn(self._drive(graph, tid, user_id, Command(resume=decision), run["kind"]))

    async def _drive(self, graph, tid: str, user_id: str, inp: Any, kind: str) -> None:
        t0 = time.time()
        db.add_event(tid, user_id, "start", {"kind": kind})
        cfg = await self.cfg(tid)
        try:
            async with self.sem:
                async for chunk in graph.astream(inp, cfg, stream_mode="updates"):
                    for node, upd in chunk.items():
                        if node == "__interrupt__":
                            db.add_event(tid, user_id, "interrupt", {"node": "approval"})
                            continue
                        tr = (upd or {}).get("trace") or []
                        db.add_event(tid, user_id, "node", {"node": node, "ms": tr[-1]["ms"] if tr else 0, "detail": tr[-1] if tr else {},
                                                            "status": (upd or {}).get("status")})
        except MarketplaceDown as e:
            self._mark_down(str(e))
            db.run("update runs set status='degraded', updated=? where thread_id=?", time.time(), tid)
            db.add_event(tid, user_id, "degraded", {"error": str(e)})
            return
        except Exception as e:  # noqa: BLE001
            db.add_event(tid, user_id, "error", {"error": f"{type(e).__name__}: {e}"})
            db.run("update runs set status='dead_letter', updated=? where thread_id=?", time.time(), tid)
            return
        await self._finalize(graph, tid, user_id, kind, t0)

    async def _finalize(self, graph, tid: str, user_id: str, kind: str, t0: float) -> None:
        cfg = await self.cfg(tid)
        snap = await graph.aget_state(cfg)
        v = snap.values or {}
        status = "waiting_approval" if snap.next and snap.tasks and snap.tasks[0].interrupts else v.get("status", "done")
        if status == "degraded":
            self._mark_down("; ".join(v.get("errors", []))[:200])
        dec = v.get("decision") or {}
        job = v.get("job") or {}
        q = v.get("price_quote") or {}
        fit, risk = v.get("fit_report") or {}, v.get("risk_report") or {}
        usage = llm.usage_snapshot()
        tokens = sum(u["tokens_in"] + u["tokens_out"] for u in usage.values())
        usd = sum(u["usd"] for u in usage.values())
        db.run("""update runs set status=?, decision=?, fit=?, risk=?, bid=?, connects=?, title=?, category=?, tokens=?, usd=?, latency_ms=?, updated=?, proposal_id=?, summary=?
                  where thread_id=?""", status, dec.get("action"), fit.get("score"), risk.get("score"), q.get("bid_amount"), q.get("connects_cost"),
               job.get("title") or v.get("proposal_id") or tid, job.get("category"), tokens, usd, int((time.time() - t0) * 1000), time.time(),
               (v.get("submission") or {}).get("proposal_id") or v.get("proposal_id"), json.dumps(dict(reasons=dec.get("reasons"), flags=risk.get("flags"))), tid)
        if v.get("submission"):
            db.run("insert or replace into pipeline values(?,?,?,?,?,?,?)", user_id, v["submission"]["proposal_id"], job.get("job_id"),
                   job.get("title"), job.get("category"), "submitted", time.time())
        write_trace(tid, v.get("trace_id", tid), v, self.hub.calls)
        db.add_event(tid, user_id, "done", {"status": status})

    # ---------------- conversation threads ----------------
    async def start_conversation(self, user: dict, proposal_id: str) -> str:
        n = db.q1("select count(*) c from runs where kind='conversation' and user_id=? and proposal_id=?", user["id"], proposal_id)["c"]
        tid = f"{user['id']}.conv.{proposal_id}.{n}"
        db.run("insert into runs(thread_id,user_id,kind,job_id,proposal_id,title,status,created,updated) values(?,?,?,?,?,?,?,?,?)",
               tid, user["id"], "conversation", None, proposal_id, f"Reply to {proposal_id}", "queued", time.time(), time.time())
        init = dict(user_id=user["id"], persona=user["persona"], thread_id=tid, trace_id=uuid.uuid4().hex[:12], proposal_id=proposal_id, steps=0)
        self._spawn(self._drive(self.conv, tid, user["id"], init, "conversation"))
        return tid

    # ---------------- scanning / pipeline sync ----------------
    async def scan(self, user: dict, limit: int = 8) -> list[str]:
        """Scout: run each saved search, queue unseen jobs (bounded per scan to stay polite)."""
        started: list[str] = []
        try:
            for s in user["settings"].get("saved_searches", []):
                res = await self.hub.call("scout", "marketplace.search_jobs", {"query": s.get("query", ""), "limit": min(limit * 3, 50)}, user=user["id"])
                for j in res["jobs"]:
                    if len(started) >= limit:
                        return started
                    if j.get("category") and j["category"] != _cat_of(user["persona"]):
                        continue
                    started.append(await self.start_bid(user, j["job_id"]))
            self._mark_up()
        except MarketplaceDown as e:
            self._mark_down(str(e))
            self.pending_scans.add(user["id"])               # queue the scan; the health loop re-runs it on recovery
        return started

    async def sync_pipeline(self, user: dict) -> int:
        try:
            props = (await self.hub.call("system", "marketplace.list_proposals", {}, user=user["id"]))["proposals"]
        except MarketplaceDown as e:
            self._mark_down(str(e))
            return 0
        self._mark_up()
        n = 0
        for p in props:
            row = db.q1("select status from pipeline where user_id=? and proposal_id=?", user["id"], p["proposal_id"])
            status = "viewed" if p["status"] == "submitted" and (p.get("status_detail") or {}).get("viewed") else p["status"]
            if row and row["status"] != status:
                db.run("update pipeline set status=?, updated=? where user_id=? and proposal_id=?", status, time.time(), user["id"], p["proposal_id"])
                n += 1
                from agent.memory.promotion_rules import record_outcome
                cat = db.q1("select category from pipeline where user_id=? and proposal_id=?", user["id"], p["proposal_id"])["category"] or "other"
                if p["status"] in ("replied", "interview", "hired"):
                    record_outcome(user["id"], cat, p["status"], p["proposal_id"])
        return n

    # ---------------- degraded mode / recovery ----------------
    def _mark_down(self, err: str) -> None:
        self.marketplace_ok, self.marketplace_error = False, err

    def _mark_up(self) -> None:
        self.marketplace_ok, self.marketplace_error = True, None

    async def health_once(self) -> bool:
        try:
            await self.hub.call("system", "marketplace.get_connects_balance", {}, user="health-check", retries_override=0)
        except Exception as e:  # noqa: BLE001
            self._mark_down(str(e))
            return False
        was_down = not self.marketplace_ok
        self._mark_up()
        if was_down:
            await self.redrive_degraded()
        return True

    async def redrive_degraded(self) -> int:
        for uid in list(self.pending_scans):
            self.pending_scans.discard(uid)
            u = db.q1("select id,persona,settings from users where id=?", uid)
            if u:
                u["settings"] = json.loads(u["settings"])
                await self.scan(u)
        rows = db.q("select thread_id,user_id,job_id from runs where status='degraded' and kind='bid'")
        for r in rows:
            u = db.q1("select id,persona,settings from users where id=?", r["user_id"])
            if not u:
                continue
            u["settings"] = json.loads(u["settings"])
            db.run("update runs set status='superseded' where thread_id=?", r["thread_id"])
            await self.start_bid(u, r["job_id"], force_new=True)
        return len(rows)

    def start_health_loop(self, interval: float = 15.0) -> None:
        async def loop():
            while True:
                await asyncio.sleep(interval)
                await self.health_once()
        self._health_task = asyncio.create_task(loop())

    async def recover(self) -> int:
        """After a crash: threads that were mid-run continue from their last checkpoint (nothing is re-sent: keys are deterministic)."""
        rows = db.q("select thread_id,user_id,kind from runs where status in ('running','queued')")
        for r in rows:
            graph = self.bid if r["kind"] == "bid" else self.conv
            self._spawn(self._drive(graph, r["thread_id"], r["user_id"], None, r["kind"]))
        return len(rows)

    async def pending_payload(self, tid: str) -> dict | None:
        run = db.q1("select kind from runs where thread_id=?", tid)
        if not run:
            return None
        graph = self.bid if run["kind"] == "bid" else self.conv
        snap = await graph.aget_state(await self.cfg(tid))
        return snap.tasks[0].interrupts[0].value if snap.tasks and snap.tasks[0].interrupts else None

    async def state_values(self, tid: str) -> dict:
        run = db.q1("select kind from runs where thread_id=?", tid)
        graph = self.bid if run and run["kind"] == "bid" else self.conv
        return (await graph.aget_state(await self.cfg(tid))).values or {}


def _cat_of(persona: str) -> str:
    return {"ai_ml_engineer": "ai_ml", "fullstack_web_dev": "web_dev", "data_analyst": "data_analytics"}[persona]
