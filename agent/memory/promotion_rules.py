"""Explicit promotion rules (R7). Nothing enters long-term memory except through these functions.

STYLE RULE   An edit PATTERN becomes a style rule only when it was observed in >= `min_occurrences` edits on
             >= `min_distinct_jobs` DIFFERENT jobs (config: memory.style). One-off edits stay as events.
OUTCOME RULE A job category's outcome stats are surfaced only after >= `min_samples_per_category` outcomes.
Both thresholds live in agent/config.yaml. Everything promoted records why (support count, job ids, timestamp).
"""
from __future__ import annotations

import re
import time

from agent.config import load_config
from agent.memory.store import get_store

FLUFF = {"passionate", "excited", "hardworking", "hard-working", "expert", "guru", "ninja", "rockstar", "dedicated", "motivated", "synergy"}


def _sentences(t: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", t.strip()) if s.strip()]


def diff_patterns(original: str, edited: str) -> list[str]:
    """Turn a (draft, user-edit) pair into candidate style patterns. Deterministic and inspectable."""
    pats = []
    o, e = _sentences(original), _sentences(edited)
    if o and e and o[0] not in e and len(e) < len(o):
        pats.append("cut_first_sentence")
    removed = set(re.findall(r"[a-z\-]+", original.lower())) - set(re.findall(r"[a-z\-]+", edited.lower()))
    pats += [f"never_say:{w}" for w in sorted(removed & FLUFF)]
    if len(edited) < 0.8 * len(original):
        pats.append("shorter")
    return pats


def record_edit(user_id: str, job_id: str, original: str, edited: str) -> dict:
    """Store observations as EVENTS, then apply the promotion rule. Returns {observed, promoted}."""
    store, cfg = get_store(), load_config()["memory"]["style"]
    promoted = []
    pats = diff_patterns(original, edited)
    for p in pats:
        key = re.sub(r"[^a-z0-9_:-]", "_", p)
        cur = store.get(("style_events", user_id), key)
        val = cur.value if cur else dict(pattern=p, jobs=[], count=0)
        if job_id not in val["jobs"]:
            val["jobs"].append(job_id)
        val["count"] += 1
        store.put(("style_events", user_id), key, val)
        if should_promote_style(val["count"], len(val["jobs"]), cfg):
            store.put(("style", user_id), key, dict(rule=p, support=val["count"], jobs=val["jobs"], promoted_at=time.time(),
                                                      why=f"seen {val['count']}x on {len(val['jobs'])} jobs (>= {cfg['min_occurrences']}x/{cfg['min_distinct_jobs']} jobs)"))
            promoted.append(p)
    return dict(observed=pats, promoted=promoted)


def should_promote_style(count: int, distinct_jobs: int, cfg: dict | None = None) -> bool:
    cfg = cfg or load_config()["memory"]["style"]
    return count >= cfg["min_occurrences"] and distinct_jobs >= cfg["min_distinct_jobs"]


def style_rules(user_id: str) -> list[str]:
    return [i.value["rule"] for i in get_store().search(("style", user_id), limit=100)]


def apply_style(text: str, rules: list[str]) -> str:
    """Apply promoted rules to a draft (Writer calls this)."""
    sents = _sentences(text)
    if "cut_first_sentence" in rules and len(sents) > 2:
        sents = sents[1:]
    for r in rules:
        if r.startswith("never_say:"):
            w = r.split(":", 1)[1]
            sents = [s for s in sents if w not in s.lower()] or sents
    return " ".join(sents)


# ---------------- outcome memory ----------------
def record_outcome(user_id: str, category: str, status: str, job_id: str) -> None:
    """status: replied | interview | hired | ignored | lost. Raw events are NOT stored, only counters."""
    store = get_store()
    cur = store.get(("outcome", user_id, category), "stats")
    v = cur.value if cur else dict(samples=0, replied=0, hired=0, jobs=[])
    if job_id in v["jobs"]:
        return
    v["jobs"].append(job_id)
    v["samples"] += 1
    v["replied"] += int(status in ("replied", "interview", "hired"))
    v["hired"] += int(status == "hired")
    store.put(("outcome", user_id, category), "stats", v)


def outcome_stats(user_id: str, category: str) -> dict | None:
    """Promotion rule: only visible once enough samples exist."""
    cur = get_store().get(("outcome", user_id, category), "stats")
    if not cur or cur.value["samples"] < load_config()["memory"]["outcome"]["min_samples_per_category"]:
        return None
    v = cur.value
    return dict(samples=v["samples"], reply_rate=round(v["replied"] / v["samples"], 3), hire_rate=round(v["hired"] / v["samples"], 3))
