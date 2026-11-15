from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request

from apps.api import db
from apps.api.auth.users import User
from apps.api.schemas.models import RunRow

router = APIRouter(tags=["jobs"])


def _row(r: dict) -> RunRow:
    r = dict(r)
    r["summary"] = json.loads(r["summary"]) if r.get("summary") else None
    return RunRow(**{k: r.get(k) for k in RunRow.model_fields if k in r})


@router.get("/jobs", response_model=list[RunRow])
def inbox(decision: str | None = None, status: str | None = None, user: dict = User):
    """Inbox: bid runs ranked by fit, with risk, recommended action, price and Connects cost."""
    rows = db.q("select * from runs where user_id=? and kind='bid' and status!='superseded' order by coalesce(fit,-1) desc, updated desc", user["id"])
    out = [_row(r) for r in rows]
    if decision:
        out = [r for r in out if r.decision == decision]
    if status:
        out = [r for r in out if r.status == status]
    return out


@router.post("/jobs/scan")
async def scan(request: Request, user: dict = User):
    started = await request.app.state.runner.scan(user)
    return {"queued": len(started), "thread_ids": started, "marketplace_ok": request.app.state.runner.marketplace_ok}


@router.post("/jobs/{job_id}/analyse")
async def analyse(job_id: str, request: Request, user: dict = User):
    tid = await request.app.state.runner.start_bid(user, job_id)
    return {"thread_id": tid}


@router.get("/jobs/{thread_id}")
async def job_detail(thread_id: str, request: Request, user: dict = User):
    run = db.q1("select * from runs where thread_id=? and user_id=?", thread_id, user["id"])
    if not run:
        raise HTTPException(404, "unknown job thread")
    v = await request.app.state.runner.state_values(thread_id)
    return dict(run=_row(run), job=v.get("job"), job_spec=v.get("job_spec"), risk_report=v.get("risk_report"), fit_report=v.get("fit_report"),
                decision=v.get("decision"), price_quote=v.get("price_quote"), evidence=v.get("evidence", []), errors=v.get("errors", []))


@router.post("/jobs/{thread_id}/skip")
def skip(thread_id: str, user: dict = User):
    run = db.q1("select status from runs where thread_id=? and user_id=?", thread_id, user["id"])
    if not run:
        raise HTTPException(404, "unknown job thread")
    db.run("update runs set status='skipped', decision='skip' where thread_id=?", thread_id)
    db.run("insert into feedback(user_id,thread_id,kind,reason,ts) values(?,?,?,?,strftime('%s','now'))", user["id"], thread_id, "user_skip", "skipped by user")
    return {"ok": True}
