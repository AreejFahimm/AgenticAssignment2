"""Human-in-the-loop nodes (R4, C5): prepare preview -> interrupt() -> process decision -> submit exactly once.

NOTHING reaches the marketplace before interrupt() returns an approval. Submit keys are derived from the thread id,
so a crash/replay/retry after approval can never submit twice or spend Connects twice (viva item 2).
"""
from __future__ import annotations

import time

from langgraph.types import interrupt

from agent.config import load_config
from agent.memory.promotion_rules import record_edit
from agent.nodes.compliance import check_text
from agent.runtime import rt_of, tr


def _final_text(state) -> str:
    return state["compliance_verdict"]["cleaned_text"]


async def prepare_approval(state, config):
    """Compute the dry_run preview BEFORE the interrupt (the interrupt node itself re-executes on resume)."""
    t, rt = time.time(), rt_of(config)
    d, q, job = state["proposal_draft"], state["price_quote"], state["job"]
    preview = await rt.hub.call("submitter", "marketplace.create_proposal_draft", dict(
        job_id=job["job_id"], cover_letter=_final_text(state), bid_amount=q["bid_amount"], dry_run=True,
        idempotency_key=f"{state['thread_id']}:draft", screening_answers=d.get("screening_answers", [])), user=state["user_id"],
        trace_id=state.get("trace_id", ""))
    bal = await rt.hub.call("submitter", "marketplace.get_connects_balance", {}, user=state["user_id"], trace_id=state.get("trace_id", ""))
    settings = state.get("settings", {})
    cost = preview["connects_cost"]
    over = settings.get("weekly_connects_budget") is not None and settings.get("connects_spent_this_week", 0) + cost > settings["weekly_connects_budget"]
    out = dict(dry_run_preview=dict(preview, balance=bal["balance"], balance_after=bal["balance"] - cost, over_weekly_budget=over),
               steps=1, trace=[tr("prepare_approval", t, connects=cost, over_budget=over)])
    if over or bal["balance"] < cost:
        out["status"] = "needs_attention"
    else:
        out["status"] = "waiting_approval"
    return out


async def approval(state, config):
    t = time.time()
    if state.get("status") == "needs_attention":
        return dict(steps=1, trace=[tr("approval", t, skipped="needs_attention")])
    payload = dict(  # everything the approval screen needs (C5)
        kind="proposal", job_id=state["job"]["job_id"], thread_id=state["thread_id"], draft=state["proposal_draft"],
        evidence=state.get("evidence", []), claim_verification=state.get("claim_verification", []),
        risk_report=state["risk_report"], price_quote=state["price_quote"], compliance=state["compliance_verdict"],
        dry_run_preview=state["dry_run_preview"], critiques=state.get("critiques", []), final_text=_final_text(state),
        error=state.get("approval_error"))
    decision = interrupt(payload)  # <- graph pauses here; state persisted in the checkpointer
    status = decision.get("status")
    out = dict(approval=decision, steps=1, approval_error=None)
    if status == "rejected":
        out.update(status="rejected", trace=[tr("approval", t, decision="rejected", reason=decision.get("reason"))])
        return out
    if status == "edited":
        edited = decision["edited_text"]
        mem = record_edit(state["user_id"], state["job"]["job_id"], _final_text(state), edited)
        v = check_text(edited, load_config()["compliance"], (config.get("configurable") or {}).get("platform_policy", {}))
        out["trace"] = [tr("approval", t, decision="edited", style=mem)]
        out["compliance_verdict"] = v.model_dump()
        if v.blocked:
            out.update(status="waiting_approval", approval_error=f"edit blocked by compliance: {v.reason}")
        else:
            out.update(status="approved")
        return out
    out.update(status="approved", trace=[tr("approval", t, decision="approved")])
    return out


def route_after_approval(state) -> str:
    s = state.get("status")
    if s == "approved":
        return "submit"
    if s == "waiting_approval":  # blocked edit -> ask again
        return "approval"
    return "__end__"


async def submit(state, config):
    """Only reachable after human approval. Idempotency keys come from the thread id (exactly-once)."""
    t, rt = time.time(), rt_of(config)
    if state.get("status") != "approved":
        return dict(trace=[tr("submit", t, refused="not approved")])
    q, job = state["price_quote"], state["job"]
    tid = state["thread_id"]
    draft = await rt.hub.call("submitter", "marketplace.create_proposal_draft", dict(
        job_id=job["job_id"], cover_letter=_final_text(state), bid_amount=q["bid_amount"], idempotency_key=f"{tid}:draft",
        screening_answers=state["proposal_draft"].get("screening_answers", [])), user=state["user_id"], trace_id=state.get("trace_id", ""))
    sub = await rt.hub.call("submitter", "marketplace.submit_proposal", dict(proposal_id=draft["proposal_id"], idempotency_key=f"{tid}:submit"),
                            user=state["user_id"], trace_id=state.get("trace_id", ""))
    return dict(submission=dict(proposal_id=draft["proposal_id"], status=sub["status"], connects_cost=draft["connects_cost"]),
                status="submitted", steps=1, trace=[tr("submit", t, proposal_id=draft["proposal_id"])])
