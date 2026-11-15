from __future__ import annotations

import json
from collections import Counter, defaultdict

from fastapi import APIRouter, Request

from agent.memory.promotion_rules import outcome_stats
from agent.memory.store import delete_memory, list_memory
from apps.api import db
from apps.api.auth.users import User
from apps.api.schemas.models import StatusOut

router = APIRouter(tags=["analytics"])
STAGES = ["drafted", "submitted", "viewed", "replied", "interview", "hired", "lost"]


def _p95(xs: list[float]) -> float:
    return sorted(xs)[min(int(len(xs) * 0.95), len(xs) - 1)] if xs else 0.0


@router.get("/pipeline")
async def pipeline(request: Request, user: dict = User):
    await request.app.state.runner.sync_pipeline(user)
    cols = {s: [] for s in STAGES}
    for r in db.q("select * from runs where user_id=? and kind='bid' and status='waiting_approval'", user["id"]):
        cols["drafted"].append(dict(id=r["thread_id"], title=r["title"], category=r["category"], bid=r["bid"], thread_id=r["thread_id"]))
    for p in db.q("select * from pipeline where user_id=? order by updated desc", user["id"]):
        stage = p["status"] if p["status"] in cols else ("lost" if p["status"] in ("rejected", "closed") else "submitted")
        cols[stage].append(dict(id=p["proposal_id"], title=p["title"], category=p["category"], proposal_id=p["proposal_id"]))
    return cols


@router.get("/analytics")
async def analytics(request: Request, user: dict = User):
    uid = user["id"]
    await request.app.state.runner.sync_pipeline(user)
    runs = db.q("select * from runs where user_id=? and kind='bid'", uid)
    pipe = db.q("select * from pipeline where user_id=?", uid)
    by_cat: dict = defaultdict(lambda: dict(submitted=0, replied=0, hired=0, connects=0))
    for p in pipe:
        c = by_cat[p["category"] or "other"]
        c["submitted"] += 1
        c["replied"] += p["status"] in ("replied", "interview", "hired")
        c["hired"] += p["status"] == "hired"
    for r in runs:
        if r["status"] == "submitted" and r["category"]:
            by_cat[r["category"]]["connects"] += r["connects"] or 0
    proposals = [r for r in runs if r["decision"] == "bid"]
    rejections = Counter(f["reason"] for f in db.q("select reason from feedback where user_id=?", uid))
    for r in runs:
        if r["summary"] and r["decision"] == "skip":
            for reason in (json.loads(r["summary"]).get("reasons") or [])[:1]:
                rejections["auto-skip: " + reason.split(":")[0].split(" ")[0] + " " + reason.split(" ")[0]] += 1
    return dict(
        funnel=dict(analysed=len(runs), skipped=sum(r["decision"] == "skip" for r in runs), bid=len(proposals), submitted=len(pipe)),
        by_category={k: dict(v, reply_rate=round(v["replied"] / v["submitted"], 3) if v["submitted"] else None,
                             hire_rate=round(v["hired"] / v["submitted"], 3) if v["submitted"] else None) for k, v in by_cat.items()},
        connects=dict(spent=sum(v["connects"] for v in by_cat.values()), budget=user["settings"].get("weekly_connects_budget")),
        cost_latency=dict(proposals=len(proposals), avg_usd=round(sum(r["usd"] or 0 for r in proposals) / len(proposals), 5) if proposals else 0,
                          p95_latency_s=round(_p95([(r["latency_ms"] or 0) / 1000 for r in proposals]), 2),
                          avg_tokens=round(sum(r["tokens"] or 0 for r in proposals) / len(proposals)) if proposals else 0),
        top_rejection_reasons=[dict(reason=k, count=v) for k, v in rejections.most_common(8)],
        outcome_memory={c: outcome_stats(uid, c) for c in by_cat},
    )


@router.get("/memory")
def memory(user: dict = User):
    return list_memory(user["id"])


@router.delete("/memory/{namespace:path}/{key}")
def forget(namespace: str, key: str, user: dict = User):
    try:
        delete_memory(user["id"], namespace, key)
    except PermissionError:
        from fastapi import HTTPException
        raise HTTPException(403, "not your memory") from None
    return {"deleted": True}


@router.get("/status", response_model=StatusOut)
def status(request: Request, user: dict = User):
    from agent.config import load_config
    r = request.app.state.runner
    return StatusOut(marketplace_ok=r.marketplace_ok, marketplace_error=r.marketplace_error,
                     queued_degraded=db.q1("select count(*) c from runs where status='degraded' and user_id=?", user["id"])["c"] + (user["id"] in r.pending_scans),
                     mode=load_config()["marketplace"]["mode"], model_profile=load_config()["models"]["profile"])


@router.post("/status/check", response_model=StatusOut)
async def check_now(request: Request, user: dict = User):
    """'Retry now' in the degraded-mode banner: probes the marketplace and re-drives queued (degraded) runs if it is back."""
    await request.app.state.runner.health_once()
    return status(request, user)
