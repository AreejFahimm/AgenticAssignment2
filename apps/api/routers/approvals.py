from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from apps.api import db
from apps.api.auth.users import User
from apps.api.schemas.models import ApprovalIn

router = APIRouter(tags=["approvals"])


@router.get("/approvals")
def pending(user: dict = User):
    """All threads waiting for the human. Survives refreshes and API restarts (state lives in the checkpointer)."""
    return db.q("select thread_id,kind,title,job_id,proposal_id,bid,connects,updated from runs where user_id=? and status='waiting_approval' order by updated desc", user["id"])


@router.get("/approvals/{thread_id}")
async def payload(thread_id: str, request: Request, user: dict = User):
    if not db.q1("select 1 from runs where thread_id=? and user_id=?", thread_id, user["id"]):
        raise HTTPException(404, "unknown thread")
    p = await request.app.state.runner.pending_payload(thread_id)
    if p is None:
        raise HTTPException(409, "nothing is waiting for approval on this thread")
    return p


@router.post("/approvals/{thread_id}", status_code=202)
async def decide(thread_id: str, body: ApprovalIn, request: Request, user: dict = User):
    """Approve / edit / reject: resumes the interrupted LangGraph thread. A repeated click returns 409 (never double-submits)."""
    if body.status == "edited" and not body.edited_text:
        raise HTTPException(422, "edited_text is required when editing")
    if body.status == "rejected":
        db.run("insert into feedback(user_id,thread_id,kind,reason,ts) values(?,?,?,?,strftime('%s','now'))", user["id"], thread_id, "reject", body.reason or "no reason given")
    try:
        await request.app.state.runner.resume(user["id"], thread_id, body.model_dump(exclude_none=True))
    except KeyError:
        raise HTTPException(404, "unknown thread") from None
    except ValueError as e:
        raise HTTPException(409, str(e)) from None
    return {"accepted": True}
