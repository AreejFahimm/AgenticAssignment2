"""Risk Assessor: client quality + scam / free-work / off-platform / injected-instruction flags."""
from __future__ import annotations

import re
import time

from agent import llm
from agent.handoffs import RiskReport
from agent.mcp_client import MarketplaceDown
from agent.runtime import rt_of, tr
from agent.security import detect_injection, wrap_untrusted

RULES = {
    "off_platform_contact": r"whatsapp|telegram|skype|wechat|signal app|(?:email|mail|contact|message) me (?:at|on)|outside (?:the )?platform|pay(?:ment)? outside|external messaging",
    "free_work": r"for free|unpaid|free (?:trial|test|sample)|before we sign|complete (?:the )?full .* free",
    "upfront_fee": r"onboarding fee|gift card|pay (?:a )?\$?\d+ .*(?:fee|deposit)|registration fee|crypto(?:currency)? payment",
}


async def risk_assessor(state, config):
    t, rt = time.time(), rt_of(config)
    job = state["job"]
    text = f"{job['title']} {job.get('description', '')}"
    flags = [name for name, pat in RULES.items() if re.search(pat, text, re.I)]
    inj = detect_injection(text)
    if inj:
        flags.append("injected_instructions")
    b = job.get("budget", {})
    if (b.get("max") or b.get("min") or 0) == 0 and b.get("type") == "fixed":
        flags.append("zero_budget")
    quality, degraded = 0.5, False
    try:
        h = await rt.hub.call("risk_assessor", "marketplace.get_client_history", {"client_id": job["client_id"]},
                              user=state["user_id"], trace_id=state.get("trace_id", "")) if job.get("client_id") else None
    except MarketplaceDown:
        h, degraded = None, True
    if h:
        quality = min(1.0, 0.25 * h["payment_verified"] + 0.35 * (h["average_rating"] / 5) + 0.2 * min(h["completed_projects"] / 20, 1)
                      + 0.2 * min(h["total_spent_usd"] / 10000, 1))
        if not h["payment_verified"]:
            flags.append("unverified_payment")
    score = min(1.0, 0.35 * ("off_platform_contact" in flags) + 0.4 * ("free_work" in flags) + 0.5 * ("upfront_fee" in flags)
                + 0.3 * ("injected_instructions" in flags) + 0.25 * ("zero_budget" in flags) + 0.2 * (1 - quality))
    scam = any(f in flags for f in ("upfront_fee", "free_work", "off_platform_contact"))
    rep = RiskReport(score=round(score, 3), flags=flags, scam=scam, injection_detected=bool(inj), client_quality=round(quality, 3),
                     explanation=f"flags={flags}; client_quality={quality:.2f}" + ("; client history unavailable (degraded)" if degraded else ""))
    if llm.enabled("risk_assessor"):
        try:  # LLM can only ADD flags, never clear rule-based ones
            d = llm.complete_json("risk_assessor", wrap_untrusted(text, "job_post") + f"\nClient quality: {quality:.2f}")
            rep.flags = sorted(set(rep.flags) | set(d.get("flags", [])))
            rep.scam = rep.scam or bool(d.get("scam"))
            rep.score = max(rep.score, float(d.get("score", 0)))
        except Exception:  # noqa: BLE001
            pass
    return dict(risk_report=rep.model_dump(), degraded=degraded, steps=1, trace=[tr("risk_assessor", t, flags=rep.flags, degraded=degraded)])
