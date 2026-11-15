"""Conversation graph (C1): ONE THREAD PER CLIENT CONVERSATION.

  liaison (read msgs, classify, draft, slots) -> approval (interrupt) -> send (message + tentative hold) -> END

Messages are only sent after the human approves in the UI. `send` keys are derived from the thread id + message count,
so replays never double-send.
"""
from __future__ import annotations

import time

from langgraph.errors import GraphBubbleUp
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy, interrupt

from agent.nodes.client_liaison import liaison
from agent.runtime import rt_of, tr
from agent.state import ConversationState


async def conv_approval(state, config):
    t = time.time()
    if state.get("status") != "waiting_approval":
        return dict(trace=[tr("approval", t, skipped=state.get("status"))])
    d = interrupt(dict(kind="message", proposal_id=state["proposal_id"], thread_id=state["thread_id"], messages=state["messages"],
                       intent=state["intent"], draft_reply=state["draft_reply"], slots=state["slots"], risk_flags=state["risk_flags"]))
    if d.get("status") == "rejected":
        return dict(approval=d, status="rejected", steps=1, trace=[tr("approval", t, decision="rejected")])
    text = d.get("edited_text") or state["draft_reply"]
    return dict(approval=dict(d, final_text=text), status="approved", steps=1, trace=[tr("approval", t, decision=d.get("status"))])


async def send(state, config):
    t, rt = time.time(), rt_of(config)
    if state.get("status") != "approved":
        return dict(trace=[tr("send", t, refused=state.get("status"))])
    text = state["approval"]["final_text"]
    n = len(state["messages"])
    key = f"{state['thread_id']}:msg{n}"
    await rt.hub.call("messenger", "marketplace.send_message", dict(proposal_id=state["proposal_id"], text=text, idempotency_key=key),
                            user=state["user_id"], trace_id=state.get("trace_id", ""))
    hold = None
    if state["intent"] == "interview_request" and state.get("slots") and state["approval"].get("slot_start"):
        hold = await rt.hub.call("client_liaison", "workspace.create_tentative_hold",
                                 dict(start_iso=state["approval"]["slot_start"], title="Interview (tentative)", idempotency_key=f"{state['thread_id']}:hold{n}"),
                                 user=state["user_id"], trace_id=state.get("trace_id", ""))
    return dict(sent=dict(text=text, hold=hold, key=key), status="sent", steps=1, trace=[tr("send", t, hold=bool(hold))])


def _after_liaison(state) -> str:
    return "approval" if state.get("status") == "waiting_approval" else END


def _after_approval(state) -> str:
    return "send" if state.get("status") == "approved" else END


def build_conversation_graph(checkpointer=None):
    g = StateGraph(ConversationState)
    retry = RetryPolicy(max_attempts=3, initial_interval=0.3)

    async def safe_liaison(state, config):
        try:
            return await liaison(state, config)
        except GraphBubbleUp:
            raise
        except Exception as e:  # noqa: BLE001
            return dict(status="dead_letter", errors=[f"liaison: {type(e).__name__}: {e}"])

    g.add_node("liaison", safe_liaison, retry_policy=retry)
    g.add_node("approval", conv_approval)
    g.add_node("send", send, retry_policy=retry)
    g.add_edge(START, "liaison")
    g.add_conditional_edges("liaison", _after_liaison, ["approval", END])
    g.add_conditional_edges("approval", _after_approval, ["send", END])
    g.add_edge("send", END)
    return g.compile(checkpointer=checkpointer)
