from __future__ import annotations

from fastapi import APIRouter, Request

from apps.api import db
from apps.api.auth.users import User

router = APIRouter(tags=["messages"])


@router.get("/messages")
async def threads(request: Request, user: dict = User):
    """Proposal threads with client messages + any conversation run (suggested reply) per thread."""
    runner = request.app.state.runner
    await runner.sync_pipeline(user)
    out = []
    for p in db.q("select * from pipeline where user_id=? order by updated desc", user["id"]):
        try:
            res = await runner.hub.call("system", "marketplace.list_messages", {"proposal_id": p["proposal_id"]}, user=user["id"])
        except Exception:  # noqa: BLE001
            res = {"messages": []}
        msgs = res["messages"] if isinstance(res, dict) else res
        if msgs:
            conv = db.q1("select thread_id,status from runs where user_id=? and kind='conversation' and proposal_id=? order by created desc", user["id"], p["proposal_id"])
            out.append(dict(proposal_id=p["proposal_id"], title=p["title"], status=p["status"], messages=msgs, conversation=conv))
    return out


@router.post("/messages/{proposal_id}/draft")
async def draft(proposal_id: str, request: Request, user: dict = User):
    tid = await request.app.state.runner.start_conversation(user, proposal_id)
    return {"thread_id": tid}
