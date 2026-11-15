"""Client Liaison (conversation graph): read client replies, classify intent, draft a reply / interview slots.

Client messages are UNTRUSTED: injection patterns are neutralised before drafting; scam signals (off-platform
contact / payment asks) are classified `scam_signal` and the reply declines politely and keeps it on-platform.
"""
from __future__ import annotations

import re
import time

from agent import llm
from agent.mcp_client import MarketplaceDown
from agent.runtime import rt_of, tr
from agent.security import detect_injection, neutralise, wrap_untrusted

INTENT_RULES = [
    ("scam_signal", r"whatsapp|telegram|skype|pay(?:ment)? outside|outside (?:the )?platform|gift card|crypto|send (?:me )?your (?:bank|password)|upfront fee|free (?:sample|trial|test)"),
    ("interview_request", r"\b(call|interview|meet|meeting|zoom|chat)\b.*|available|schedule|what times?|free (?:this|next) week"),
    ("negotiation", r"\b(rate|price|budget|discount|cheaper|lower|negotiate|fixed price|milestone)\b"),
    ("question", r"\?|can you|could you|do you have|have you|how (?:would|do|long)"),
]


def classify(text: str) -> str:
    low = text.lower()
    for intent, pat in INTENT_RULES:
        if re.search(pat, low):
            return intent
    return "other"


def draft_reply(intent: str, last: str, slots: list[dict]) -> str:
    if intent == "scam_signal":
        return ("Thanks for reaching out. I keep all communication and payments on the platform so both of us are protected, "
                "so I will not move to another channel or work unpaid. I am happy to continue here and agree the scope and milestones.")
    if intent == "interview_request":
        opts = "; ".join(s["start"].replace("T", " ") + " UTC" for s in slots[:3]) or "later this week"
        return f"Thanks, I would be glad to talk. These times work for me: {opts}. Let me know which suits you and I will confirm."
    if intent == "negotiation":
        return ("Thank you for the feedback on the budget. I am open to adjusting scope or splitting this into milestones "
                "so it fits your budget while keeping quality high. Which deliverables matter most to you?")
    if intent == "question":
        return "Good question. Based on my earlier work I can answer this in detail; could you share a little more context so I can be specific?"
    return "Thanks for your message. I will review it and come back to you shortly with a clear next step."


async def liaison(state, config):
    t, rt = time.time(), rt_of(config)
    try:
        msgs = await rt.hub.call("client_liaison", "marketplace.list_messages", {"proposal_id": state["proposal_id"]}, user=state["user_id"],
                                 trace_id=state.get("trace_id", ""))
    except MarketplaceDown as e:
        return dict(status="degraded", errors=[f"liaison: marketplace unavailable ({e})"], steps=1, trace=[tr("liaison", t, degraded=True)])
    msgs = msgs["messages"] if isinstance(msgs, dict) else msgs
    client_msgs = [m for m in msgs if m["from"] == "client"]
    if not client_msgs:
        return dict(status="idle", messages=msgs, steps=1, trace=[tr("liaison", t, new_messages=0)])
    last = client_msgs[-1]["text"]
    flags = ["injected_instructions"] if detect_injection(last) else []
    safe = neutralise(last)
    intent = classify(safe)
    slots = []
    if intent == "interview_request":
        s = await rt.hub.call("client_liaison", "workspace.free_calendar_slots", {"days": 5}, user=state["user_id"], trace_id=state.get("trace_id", ""))
        slots = s["slots"][:3]
    reply = draft_reply(intent, safe, slots)
    if llm.enabled("client_liaison"):
        try:
            d = llm.complete_json("client_liaison", wrap_untrusted(safe, "client_message") + f"\nFREE SLOTS: {slots}")
            reply, intent = d.get("reply", reply), d.get("intent", intent) if d.get("intent") in {i for i, _ in INTENT_RULES} | {"other"} else intent
        except Exception:  # noqa: BLE001
            pass
    if intent == "scam_signal":
        flags.append("off_platform_or_payment_ask")
    return dict(messages=msgs, intent=intent, draft_reply=reply, slots=slots, risk_flags=flags, status="waiting_approval", steps=1,
                trace=[tr("liaison", t, intent=intent, flags=flags, slots=len(slots))])
