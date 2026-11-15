"""Critic: grounding, personalisation, length. May send the draft back to the Writer at most `max_revisions` times."""
from __future__ import annotations

import time

from agent import llm
from agent.config import load_config
from agent.handoffs import Critique
from agent.runtime import tr


async def critic(state, config):
    t, cfg = time.time(), load_config()
    cc = cfg["critic"]
    d = state["proposal_draft"]
    text = d["cover_letter"]
    low = text.lower()
    issues = []
    if len(text) < cc["min_chars"]:
        issues.append(f"too short for a specific proposal ({len(text)} < {cc['min_chars']} chars): add concrete detail")
    if len(text) > cc["max_chars"]:
        issues.append(f"length {len(text)} exceeds {cc['max_chars']}")
    if any(g in low for g in cc["generic_openers"]):
        issues.append("generic opener: personalise to this client's need")
    title_tokens = [w for w in state["job_spec"]["title"].lower().split() if len(w) > 3]
    if title_tokens and not any(w in low for w in title_tokens):
        issues.append("not personalised: does not mention the job's subject")
    if state["evidence"] and not d["evidence_ids"]:
        issues.append("no evidence citations although evidence exists")
    unsup = [c for c in d["claims"] if c["label"] == "unsupported"]
    if len(unsup) > cc["max_unsupported_claims"]:
        issues.append(f"{len(unsup)} unsupported claims remain")
    if llm.enabled("critic"):
        try:
            j = llm.complete_json("critic", f"JOB: {state['job_spec']['title']}\nDRAFT:\n{text}\nISSUES FOUND: {issues}")
            issues += [i for i in j.get("issues", []) if i not in issues]
        except Exception:  # noqa: BLE001
            pass
    revisions = state.get("revisions", 0)
    send_back = bool(issues) and revisions < cfg["budgets"]["max_revisions"]
    crit = Critique(passed=not issues, issues=issues, revision_requested=send_back)
    return dict(critiques=[crit.model_dump()], revisions=revisions + (1 if send_back else 0), steps=1,
                trace=[tr("critic", t, passed=crit.passed, issues=len(issues), send_back=send_back)])


def route_after_critic(state) -> str:
    return "writer" if state["critiques"][-1]["revision_requested"] else "compliance"
