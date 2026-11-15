"""Bid graph (C1): ONE THREAD PER JOB. Hand-written LangGraph StateGraph (not a prebuilt agent).

  START -> scout -> fan-out (Send) -> [analyst | risk_assessor | fit_matcher]  (parallel)
        -> decide -> skip / watch -> END
                   -> bid -> pricing -> writer -> verifier -> critic -> (writer, at most 2x) -> compliance
        -> prepare_approval (dry_run preview) -> approval (interrupt) -> submit -> END

Guards: per-node retry policy, step/token budgets -> `needs_attention`, MarketplaceDown -> degraded state,
unhandled errors -> `dead_letter`. The graph can only reach `submit` through the human approval node.
"""
from __future__ import annotations

import functools
import os
from collections.abc import Awaitable, Callable

from langgraph.errors import GraphBubbleUp
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy, Send

from agent import llm
from agent.config import load_config
from agent.mcp_client import MarketplaceDown
from agent.nodes.analyst import analyst
from agent.nodes.approval import approval, prepare_approval, route_after_approval, submit
from agent.nodes.compliance import compliance
from agent.nodes.critic import critic, route_after_critic
from agent.nodes.fit_matcher import fit_matcher
from agent.nodes.pricing import decide, pricing
from agent.nodes.risk_assessor import risk_assessor
from agent.nodes.scout import scout
from agent.nodes.verifier import verifier
from agent.nodes.writer import writer
from agent.state import GigBidState

NO_WRAP = {"submit"}  # submit must RAISE on outage so the checkpoint keeps it pending and a retry resumes it


def _tokens() -> int:
    return sum(u["tokens_in"] + u["tokens_out"] for u in llm.USAGE.values())


def _disabled() -> set[str]:
    """Evaluation-only switch (R&D question C ablation): GIGBID_DISABLE=risk_assessor,verifier,critic,compliance replaces those nodes with pass-throughs."""
    return {x for x in os.getenv("GIGBID_DISABLE", "").split(",") if x}


_PASS = {
    "risk_assessor": lambda st: dict(risk_report=dict(score=0.0, flags=[], explanation="disabled", scam=False, injection_detected=False, client_quality=0.5)),
    "verifier": lambda st: dict(claim_verification=[]),
    "critic": lambda st: dict(critiques=[dict(passed=True, issues=[], revision_requested=False)]),
    "compliance": lambda st: dict(compliance_verdict=dict(passed=True, blocked=False, violations=[], reason="", cleaned_text=st["proposal_draft"]["cover_letter"])),
}


def guarded(name: str, fn: Callable[..., Awaitable[dict]]):
    """Budget enforcement (C4) + failure handling (C7)."""
    @functools.wraps(fn)
    async def inner(state, config):
        if name in _disabled() and name in _PASS:
            return dict(_PASS[name](state), steps=1)
        b = load_config()["budgets"]
        if state.get("steps", 0) >= b["max_graph_steps"] or state.get("tokens", 0) > b["max_tokens_per_job"]:
            return dict(status="needs_attention", errors=[f"budget exceeded before {name}: steps={state.get('steps', 0)}, tokens={state.get('tokens', 0)}"])
        before = _tokens()
        try:
            out = await fn(state, config)
        except GraphBubbleUp:  # interrupt() / control-flow exceptions must propagate
            raise
        except MarketplaceDown as e:
            if name in NO_WRAP:
                raise
            return dict(status="degraded", degraded=True, errors=[f"{name}: marketplace unavailable ({e})"])
        except Exception as e:  # noqa: BLE001  retries already exhausted by RetryPolicy -> dead letter
            if name in NO_WRAP:
                raise
            return dict(status="dead_letter", errors=[f"{name}: {type(e).__name__}: {e}"])
        used = _tokens() - before
        if used:
            out = dict(out, tokens=used)
        return out
    return inner


def fan_out(state):
    if state.get("status") == "skipped":  # duplicate
        return END
    return [Send("analyst", state), Send("risk_assessor", state), Send("fit_matcher", state)]


def after_decide(state) -> str:
    if state.get("status") in ("needs_attention", "degraded", "dead_letter"):
        return END
    return "pricing" if state["decision"]["action"] == "bid" else END


def after_pricing(state) -> str:
    return "writer" if state.get("status") == "running" else END


def after_critic(state) -> str:
    if state.get("status") in ("needs_attention", "dead_letter"):
        return END
    return route_after_critic(state)


def after_compliance(state) -> str:
    return END if state.get("status") == "blocked" else "prepare_approval"


def after_prepare(state) -> str:
    return END if state.get("status") == "needs_attention" else "approval"


def build_bid_graph(checkpointer=None):
    g = StateGraph(GigBidState)
    retry = RetryPolicy(max_attempts=3, initial_interval=0.3, backoff_factor=2.0)
    nodes = dict(scout=scout, analyst=analyst, risk_assessor=risk_assessor, fit_matcher=fit_matcher, decide=decide, pricing=pricing,
                 writer=writer, verifier=verifier, critic=critic, compliance=compliance, prepare_approval=prepare_approval,
                 approval=approval, submit=submit)
    for name, fn in nodes.items():
        g.add_node(name, guarded(name, fn), retry_policy=None if name in ("approval",) else retry)
    g.add_edge(START, "scout")
    g.add_conditional_edges("scout", fan_out, ["analyst", "risk_assessor", "fit_matcher", END])
    g.add_edge(["analyst", "risk_assessor", "fit_matcher"], "decide")  # join: waits for all three
    g.add_conditional_edges("decide", after_decide, ["pricing", END])
    g.add_conditional_edges("pricing", after_pricing, ["writer", END])
    g.add_edge("writer", "verifier")
    g.add_edge("verifier", "critic")
    g.add_conditional_edges("critic", after_critic, ["writer", "compliance", END])
    g.add_conditional_edges("compliance", after_compliance, ["prepare_approval", END])
    g.add_conditional_edges("prepare_approval", after_prepare, ["approval", END])
    g.add_conditional_edges("approval", route_after_approval, ["submit", "approval", END])
    g.add_edge("submit", END)
    return g.compile(checkpointer=checkpointer)


def render_png(path: str) -> None:  # docs/images/bid_graph.png
    build_bid_graph().get_graph().draw_mermaid_png(output_file_path=path)


def mermaid() -> str:
    return build_bid_graph().get_graph().draw_mermaid()
