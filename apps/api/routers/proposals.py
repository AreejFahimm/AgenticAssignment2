from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Request

from apps.api import db
from apps.api.auth.users import User
from apps.api.schemas.models import RegenerateIn, RegenerateOut

router = APIRouter(tags=["proposals"])


@router.get("/proposals/{thread_id}")
async def studio(thread_id: str, request: Request, user: dict = User):
    """Everything the Proposal Studio shows: draft, claim->evidence map, critic + compliance comments, dry_run preview."""
    run = db.q1("select status from runs where thread_id=? and user_id=?", thread_id, user["id"])
    if not run:
        raise HTTPException(404, "unknown thread")
    v = await request.app.state.runner.state_values(thread_id)
    if not v.get("proposal_draft"):
        raise HTTPException(409, "no draft for this job (it was skipped or is still running)")
    d = v["proposal_draft"]
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", d["cover_letter"]) if s]
    ev = {e["evidence_id"]: e for e in v.get("evidence", [])}
    paras = []
    for s in sentences:
        ids = re.findall(r"\[([^\]\s]+)\]", s)
        paras.append(dict(text=s, evidence=[ev[i] for i in ids if i in ev]))
    return dict(status=run["status"], paragraphs=paras, draft=d, claim_verification=v.get("claim_verification", []), critiques=v.get("critiques", []),
                compliance=v.get("compliance_verdict"), price_quote=v.get("price_quote"), dry_run_preview=v.get("dry_run_preview"),
                risk_report=v.get("risk_report"), evidence=list(ev.values()))


@router.post("/proposals/{thread_id}/regenerate", response_model=RegenerateOut)
async def regenerate(thread_id: str, body: RegenerateIn, request: Request, user: dict = User):
    """Regenerate ONE paragraph from a different supporting evidence item (never invents experience)."""
    if not db.q1("select 1 from runs where thread_id=? and user_id=?", thread_id, user["id"]):
        raise HTTPException(404, "unknown thread")
    v = await request.app.state.runner.state_values(thread_id)
    sents = [s for s in re.split(r"(?<=[.!?])\s+", v["proposal_draft"]["cover_letter"]) if s]
    if body.paragraph_index >= len(sents):
        raise HTTPException(422, "paragraph_index out of range")
    used = set(re.findall(r"\[([^\]\s]+)\]", " ".join(sents)))
    alt = next((e for e in v.get("evidence", []) if e["evidence_id"] not in used and e["type"] == "case_study"), None)
    if not alt:
        return RegenerateOut(paragraph_index=body.paragraph_index, text=sents[body.paragraph_index], evidence_ids=[])
    text = f"On another project, {alt['text'][0].lower() + alt['text'][1:]}".rstrip(".") + f". [{alt['evidence_id']}]"
    return RegenerateOut(paragraph_index=body.paragraph_index, text=text, evidence_ids=[alt["evidence_id"]])
