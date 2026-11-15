"""Claim verification node (B3): runs BEFORE the Critic. Unsupported claims are removed from the draft."""
from __future__ import annotations

import re
import time

from agent.runtime import tr
from rag.verify import apply_verification, unsupported_rate, verify_claims


async def verifier(state, config):
    t = time.time()
    draft = dict(state["proposal_draft"])
    text = draft["cover_letter"]
    plain = re.sub(r"\s*\[[^\]\s]+\]", "", text)  # verify the words, not the citation markers
    ev = state.get("evidence", [])
    before = verify_claims(plain, ev)
    rate_before = unsupported_rate(before)
    if rate_before > 0:
        kept = [v["claim"] for v in before if v["label"] != "unsupported"]
        # keep original sentence (with its [evidence id]) when its plain form survived
        out = [s for s in re.split(r"(?<=[.!?])\s+", text) if re.sub(r"\s*\[[^\]\s]+\]", "", s).strip() in kept]
        draft["cover_letter"] = " ".join(out) if out else apply_verification(plain, before)
    after = verify_claims(re.sub(r"\s*\[[^\]\s]+\]", "", draft["cover_letter"]), ev)
    draft["claims"] = [dict(text=v["claim"], evidence_ids=v["evidence_ids"], label=v["label"]) for v in after if v["label"] != "not_a_claim"]
    ver = [dict(v) for v in before]
    return dict(proposal_draft=draft, claim_verification=ver, steps=1,
                trace=[tr("verifier", t, unsupported_before=round(rate_before, 3), unsupported_after=round(unsupported_rate(after), 3),
                          removed=len([v for v in before if v["label"] == "unsupported"]))])
