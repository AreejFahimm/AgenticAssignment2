"""Typed graph state (C2). THREE things are kept apart:

  STATE      - what this job/conversation needs right now (this TypedDict, checkpointed per thread)
  TRACE      - every tool call/result/observation, append-only, for audit & debugging (`trace` here + Langfuse/OTel)
  MEMORY     - long-term, promoted knowledge only, in the LangGraph store (agent/memory/); raw tool output NEVER goes there

Reducers are declared on every field that parallel branches (analyst / risk / matcher) may write.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


def _merge_dict(a: dict | None, b: dict | None) -> dict:
    return {**(a or {}), **(b or {})}


class GigBidState(TypedDict, total=False):
    # identity / config for this thread
    user_id: str
    persona: str
    thread_id: str
    trace_id: str
    # job + analyses (written by parallel branches -> separate keys, merged by reducer)
    job: dict[str, Any]
    job_spec: dict[str, Any]
    risk_report: dict[str, Any]
    fit_report: dict[str, Any]
    evidence: Annotated[list[dict[str, Any]], operator.add]
    # decision / price / drafts
    decision: dict[str, Any]
    price_quote: dict[str, Any]
    proposal_draft: dict[str, Any]
    claim_verification: list[dict[str, Any]]
    critiques: Annotated[list[dict[str, Any]], operator.add]
    compliance_verdict: dict[str, Any]
    revisions: int
    # approvals / outcomes
    approval: dict[str, Any]            # {"status": approved|edited|rejected, "edited_text":..., "reason":...}
    submission: dict[str, Any]          # result of submit (exactly-once guarded by idempotency key)
    outcome: dict[str, Any]
    # control
    status: str                         # running | waiting_approval | skipped | watching | submitted | rejected | blocked | needs_attention | dead_letter
    steps: Annotated[int, operator.add]
    tokens: Annotated[int, operator.add]
    errors: Annotated[list[str], operator.add]
    degraded: bool
    # execution TRACE (append-only, separate from state used for decisions)
    trace: Annotated[list[dict[str, Any]], operator.add]
    # run settings
    autonomy: str
    dry_run_preview: dict[str, Any]
    approval_error: str | None
    settings: dict[str, Any]            # per-user: weekly_connects_budget, connects_spent_this_week, autonomy
    job_id: str
    strategy: str                       # writer strategy for A/B experiments (X2): evidence_first | concise_question


class ConversationState(TypedDict, total=False):
    user_id: str
    persona: str
    thread_id: str
    proposal_id: str
    messages: list[dict[str, Any]]
    intent: str                         # question | negotiation | interview_request | scam_signal | other
    draft_reply: str
    slots: list[dict[str, Any]]
    risk_flags: list[str]
    approval: dict[str, Any]
    sent: dict[str, Any]
    status: str
    steps: Annotated[int, operator.add]
    trace: Annotated[list[dict[str, Any]], operator.add]
    errors: Annotated[list[str], operator.add]
