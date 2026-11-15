"""Compliance Guard: enforce the policy pack. Removes contact details, guarantees and off-platform asks.

Rules are DATA (config.yaml `compliance:` + the marketplace's own /policy endpoint), so a platform-policy change
needs a config edit, not a code change. `cleaned_text` is what would be sent: evidence markers like [ev-id] are
stripped from it (they remain in the draft for the UI's evidence-on-hover).
"""
from __future__ import annotations

import re
import time

from agent.config import load_config
from agent.handoffs import ComplianceVerdict
from agent.runtime import tr
from agent.security import mask_pii

_PHONE_RAW = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{8,}\d)(?!\d)")
_EMAIL_RAW = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")  # must not swallow the sentence-final period
_URLH = re.compile(r"(?i)\b(?:whatsapp|telegram|skype|wechat)\b[^.]*\.?")


def check_text(text: str, cc: dict, platform_policy: dict | None = None) -> ComplianceVerdict:
    platform_policy = platform_policy or {}
    violations: list[str] = []
    out = re.sub(r"\s*\[[^\]\s]+\]", "", text)  # strip evidence markers
    if _EMAIL_RAW.search(out) and "email" in cc["strip_patterns"]:
        violations.append("contact detail: email removed")
        out = _EMAIL_RAW.sub("", out)
    if _PHONE_RAW.search(out) and "phone" in cc["strip_patterns"]:
        violations.append("contact detail: phone removed")
        out = _PHONE_RAW.sub("", out)
    sents = re.split(r"(?<=[.!?])\s+", out)
    keep = []
    for s in sents:
        hit = [p for p in cc["banned_phrases"] if p in s.lower()]
        if hit:
            violations.append(f"banned phrase {hit[0]!r}: sentence removed")
        else:
            keep.append(s)
    out = re.sub(r"\s+", " ", " ".join(keep)).strip()
    min_len = max(cc["min_cover_letter_chars"], platform_policy.get("min_cover_letter_chars", 0))
    blocked = False
    reason = ""
    if len(out) < min_len:
        blocked, reason = True, f"cover letter shorter than platform minimum {min_len} chars after cleaning"
    if len(out) > cc["max_cover_letter_chars"]:
        blocked, reason = True, f"cover letter longer than {cc['max_cover_letter_chars']} chars"
    if len(out) < 40:
        blocked, reason = True, "nothing left to send after compliance cleaning"
    return ComplianceVerdict(passed=not blocked, blocked=blocked, violations=violations, cleaned_text=out, reason=reason)


async def compliance(state, config):
    t, cfg = time.time(), load_config()
    pol = (config.get("configurable") or {}).get("platform_policy", {})
    text = (state.get("approval") or {}).get("edited_text") or state["proposal_draft"]["cover_letter"]
    v = check_text(text, cfg["compliance"], pol)
    v.violations = [mask_pii(x) for x in v.violations]
    out = dict(compliance_verdict=v.model_dump(), steps=1, trace=[tr("compliance", t, blocked=v.blocked, violations=len(v.violations))])
    if v.blocked:
        out["status"] = "blocked"
    return out
