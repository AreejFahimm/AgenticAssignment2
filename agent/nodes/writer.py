"""Proposal Writer: cover letter + screening answers where every experience claim cites portfolio evidence.

Offline profile = extractive, template-based writer (deterministic; uses only retrieved evidence text, so it cannot
invent experience). LLM profiles use prompts/writer.md and are then checked by claim verification (rag/verify.py).
"""
from __future__ import annotations

import re
import time

from agent import llm
from agent.handoffs import Claim, ProposalDraft
from agent.memory.promotion_rules import apply_style, style_rules
from agent.runtime import tr
from agent.security import wrap_untrusted


def _sentence(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().rstrip(".") + "."


def _project_title(e: dict) -> str:
    m = re.search(r"^#\s*(.+)$", e["text"], re.M)
    t = m.group(1) if m else e["text"].split(".")[0]
    return re.sub(r"[-_]+", " ", t).replace("(", "for a ").replace(")", " client").strip()


def _clean_req(r: str) -> str:
    return re.sub(r"^experience with\s+", "", r).strip()


def offline_draft(state: dict, issues: list[str]) -> tuple[str, list[Claim]]:
    """Strategies (X2 proposal experiments, state['strategy']):
       evidence_first (default): up to 3 cited past-work sentences + honest gaps + milestone offer
       concise_question: ONE cited sentence + a clarifying question to the client (shorter, conversation-first)"""
    spec, ev, fit = state["job_spec"], state.get("evidence", []), state["fit_report"]
    max_used = 1 if state.get("strategy") == "concise_question" else 3
    by_id = {e["evidence_id"]: e for e in ev}
    claims: list[Claim] = []
    parts = [f"Your post for \"{spec['title']}\" caught my attention."]
    used = 0
    for m in fit["matrix"]:
        if used >= max_used or not m["evidence_ids"]:
            continue
        e = by_id.get(m["evidence_ids"][0])
        if not e or e["type"] == "code":  # raw code snippets are not quotable claims
            continue
        if e["type"] == "case_study":
            sent = _sentence(f"On a past project, {e['text'][0].lower() + e['text'][1:]}")
        elif e["type"] == "review":
            sent = _sentence(f"A previous client wrote: {e['text']}")
        else:  # repo README / code: only claim what the artefact shows
            sent = _sentence(f"I have also built a related project, {_project_title(e)}")
        if any(c.text == sent for c in claims):
            continue
        parts.append(f"{sent} [{e['evidence_id']}]")
        claims.append(Claim(text=sent, evidence_ids=[e["evidence_id"]]))
        used += 1
    gaps = [_clean_req(m["requirement"]) for m in fit["matrix"] if m["strength"] == 0 and m["requirement"].startswith("experience with")][:2]
    if gaps:
        parts.append("Where my portfolio does not show exactly this yet (" + "; ".join(gaps) + "), I will say so up front and suggest a short paid milestone to de-risk it.")
    if state.get("strategy") == "concise_question":
        parts.append(f"Before I propose a plan: what does a successful first version of {spec['title'].lower()} look like for you, and what is the timeline?")
        return " ".join(parts), claims
    parts.append(f"I can deliver a first milestone for {spec['title'].lower()} and share progress with you before we go further.")
    if any("short" in i.lower() or "length" in i.lower() for i in issues):
        parts.append("To keep it concrete, I would agree acceptance criteria with you before starting and report progress at each milestone, so there are no surprises on scope or timeline.")
    if any("generic" in i.lower() or "personal" in i.lower() for i in issues):
        d = (spec["deliverables"] or [spec["title"]])[0][:140].rstrip(".")
        parts.insert(1, f"Reading the details, the key deliverable is: {d}.")
    return " ".join(parts), claims


async def writer(state, config):
    t = time.time()
    uid = state["user_id"]
    issues = state["critiques"][-1]["issues"] if state.get("critiques") else []
    rules = style_rules(uid)
    answers: list[str] = []
    if llm.enabled("writer"):
        try:
            ev_txt = "\n".join(f"[{e['evidence_id']}] {e['text']}" for e in state.get("evidence", []))
            d = llm.complete_json("writer", wrap_untrusted(f"{state['job']['title']}\n{state['job'].get('description', '')}", "job_post")
                                  + f"\nEVIDENCE:\n{ev_txt}\nSTYLE RULES: {rules}\nFIX THESE ISSUES: {issues}\nPRICE: {state['price_quote']['bid_amount']}")
            text, claims, answers = d["cover_letter"], [], d.get("screening_answers", [])
        except Exception:  # noqa: BLE001  fall back to the extractive writer
            text, claims = offline_draft(state, issues)
    else:
        text, claims = offline_draft(state, issues)
    if rules:
        text = apply_style(text, rules)
    cited = sorted(set(re.findall(r"\[([^\]\s]+)\]", text)))
    draft = ProposalDraft(job_id=state["job"]["job_id"], cover_letter=text, screening_answers=answers, evidence_ids=cited,
                          claims=claims, revision=state.get("revisions", 0))
    return dict(proposal_draft=draft.model_dump(), steps=1, trace=[tr("writer", t, revision=draft.revision, chars=len(text), style_rules=rules)])
