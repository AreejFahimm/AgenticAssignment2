from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from agent.tracing import read_trace
from apps.api import db
from apps.api.auth.users import User

router = APIRouter(tags=["runs"])

TERMINAL = {"done", "error", "degraded"}


@router.get("/runs")
def list_runs(user: dict = User):
    return db.q("select thread_id,kind,title,status,latency_ms,tokens,usd,updated from runs where user_id=? order by updated desc limit 100", user["id"])


@router.get("/runs/{thread_id}/events")
async def events(thread_id: str, request: Request, after: int = 0, user: dict = User):
    """Server-Sent Events: live node-by-node progress streamed from LangGraph (`stream_mode=updates`).
    Reconnect with ?after=<last id> after a refresh; events are persisted so nothing is lost."""
    if not db.q1("select 1 from runs where thread_id=? and user_id=?", thread_id, user["id"]):
        raise HTTPException(404, "unknown thread")

    async def gen():
        last = after
        idle = 0
        while True:
            rows = db.q("select id,ts,kind,data from run_events where thread_id=? and user_id=? and id>? order by id", thread_id, user["id"], last)
            for r in rows:
                last = r["id"]
                yield f"id: {r['id']}\nevent: {r['kind']}\ndata: {r['data']}\n\n"
                if r["kind"] in TERMINAL:
                    idle = 999
            if idle >= 999:
                return
            st = db.q1("select status from runs where thread_id=?", thread_id)
            if not rows and st and st["status"] not in ("queued", "running"):
                idle += 1
                if idle > 3:
                    return
            if await request.is_disconnected():
                return
            await asyncio.sleep(0.25)
            yield ": keepalive\n\n" if not rows else ""

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/runs/{thread_id}/trace")
def trace(thread_id: str, user: dict = User):
    if not db.q1("select 1 from runs where thread_id=? and user_id=?", thread_id, user["id"]):
        raise HTTPException(404, "unknown thread")
    t = read_trace(thread_id)
    if not t:
        raise HTTPException(404, "trace not written yet")
    return t


@router.post("/runs/{thread_id}/retry")
async def retry(thread_id: str, request: Request, user: dict = User):
    run = db.q1("select job_id,status from runs where thread_id=? and user_id=?", thread_id, user["id"])
    if not run or not run["job_id"]:
        raise HTTPException(404, "unknown thread")
    if run["status"] not in ("degraded", "dead_letter", "needs_attention"):
        raise HTTPException(409, f"thread is {run['status']}")
    db.run("update runs set status='superseded' where thread_id=?", thread_id)
    return {"thread_id": await request.app.state.runner.start_bid(user, run["job_id"], force_new=True)}
