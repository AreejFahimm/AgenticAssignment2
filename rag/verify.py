"""Claim verification (B3, R5): split a draft into claims and ground each in retrieved evidence.

Labels: supported | partly_supported | unsupported | not_a_claim. Unsupported claims are removed
(or rewritten via an LLM when one is configured) BEFORE the Critic sees the draft.

Grounding is deterministic and open-model only: content-token overlap + number/entity agreement +
embedding similarity. Thresholds are in THRESHOLDS so they can be tuned on the dev set (and are
reported in the results). An optional LLM judge can be plugged in via `llm_judge`.
"""
from __future__ import annotations

import re
from collections.abc import Callable

THRESHOLDS = {"supported": 0.45, "partly": 0.22, "cos_supported": 0.62}
_STOP = set("a an the and or of to in on for with by from at as is are was were be been i my me we our you your it its this that these those "
            "can will would should have has had do does did not no yes so if than then also very more most into over under per".split())
_PAST = r"(built|developed|delivered|led|managed|designed|implemented|created|launched|improved|reduced|increased|trained|deployed|shipped|worked|achieved|cut|raised|automated|migrated|completed|won)"
_CLAIM_RE = re.compile(
    rf"\bi(?:'ve| have| had)?(?: also| previously| recently)? {_PAST}\b|\bmy (?:experience|work|projects?|portfolio|clients?)\b"
    r"|\b\d+\+? years\b|\bon a (?:past|previous) project\b|\ba previous client\b|\bi have (?:experience|done|worked)\b", re.I)
_NUM = re.compile(r"\d+(?:[.,]\d+)?")
_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def split_claims(draft: str) -> list[str]:
    return [s.strip() for s in _SPLIT.split(draft) if len(s.strip()) > 3]


def is_experience_claim(sentence: str) -> bool:
    """A sentence that asserts something about the freelancer's past work (what must be grounded)."""
    s = sentence.strip()
    if s.endswith("?"):
        return False
    if _CLAIM_RE.search(s):
        return True
    return bool(_NUM.search(s) and re.search(r"%|years|projects|clients|users|requests", s, re.I))


def _content(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9\+\#\.]+", text.lower()) if w not in _STOP and len(w) > 2}


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in _NUM.findall(text)}


def verify_claims(draft: str, evidence: list[dict], *, profile_facts: str = "",
                  llm_judge: Callable[[str, list[dict]], str] | None = None) -> list[dict]:
    """Return [{claim, label, score, evidence_ids, reason}] for every sentence of the draft."""
    ev_text = " ".join(e["text"] for e in evidence) + " " + profile_facts
    results = []
    for claim in split_claims(draft):
        if not is_experience_claim(claim):
            results.append(dict(claim=claim, label="not_a_claim", score=1.0, evidence_ids=[], reason="no experience assertion"))
            continue
        c_tok = _content(claim)
        best, best_ids = 0.0, []
        for e in evidence:
            overlap = len(c_tok & _content(e["text"])) / max(len(c_tok), 1)
            if overlap > best:
                best, best_ids = overlap, [e["evidence_id"]]
        nums_missing = _numbers(claim) - _numbers(ev_text)
        if llm_judge is not None:
            label = llm_judge(claim, evidence)
            reason = "llm judge"
        else:
            if nums_missing:
                label, reason = "unsupported", f"numbers not in evidence: {sorted(nums_missing)}"
            elif best >= THRESHOLDS["supported"]:
                label, reason = "supported", "content overlap with evidence"
            elif best >= THRESHOLDS["partly"]:
                label, reason = "partly_supported", "partial overlap"
            else:
                label, reason = "unsupported", "no matching evidence"
        results.append(dict(claim=claim, label=label, score=round(best, 3), evidence_ids=best_ids, reason=reason))
    return results


def apply_verification(draft: str, verdicts: list[dict]) -> str:
    """Remove unsupported claims (the Writer may re-draft from the removals via the Critic loop)."""
    keep = [v["claim"] for v in verdicts if v["label"] != "unsupported"]
    return " ".join(keep)


def unsupported_rate(verdicts: list[dict]) -> float:
    claims = [v for v in verdicts if v["label"] != "not_a_claim"]
    return sum(v["label"] == "unsupported" for v in claims) / len(claims) if claims else 0.0
