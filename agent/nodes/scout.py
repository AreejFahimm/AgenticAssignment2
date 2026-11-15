"""Scout: runs saved searches, de-duplicates, queues new jobs (marketplace read only)."""
from __future__ import annotations

import hashlib
import re
import sqlite3
import time

from agent.config import ROOT
from agent.runtime import rt_of, tr


class SeenStore:
    """Persistent dedup (exact + near-duplicate by normalised title/description hash). Idempotent re-scans."""

    def __init__(self, path: str | None = None):
        p = path or str(ROOT / "data" / "processed" / "seen_jobs.sqlite")
        self.c = sqlite3.connect(p, check_same_thread=False, isolation_level=None)
        self.c.execute("create table if not exists seen(user text, h text, job_id text, primary key(user,h))")

    @staticmethod
    def fingerprint(job: dict) -> str:
        key = re.sub(r"[^a-z0-9]", "", (re.sub(r"\(urgent\)|- repost|!!", "", job.get("title", "").lower()) + job.get("description", "")[:200].lower()))
        return hashlib.md5(key.encode()).hexdigest()

    def check_and_add(self, user: str, job: dict) -> str | None:
        """Returns the original job_id if this is a duplicate, else None (and records it)."""
        h = self.fingerprint(job)
        row = self.c.execute("select job_id from seen where user=? and h=?", (user, h)).fetchone()
        if row and row[0] != job["job_id"]:
            return row[0]
        self.c.execute("insert or ignore into seen values(?,?,?)", (user, h, job["job_id"]))
        return None


async def scout(state, config):
    t, rt = time.time(), rt_of(config)
    job = state.get("job")
    if not job:  # thread started with only a job id
        job = await rt.hub.call("scout", "marketplace.get_job", {"job_id": state["job_id"]}, user=state["user_id"],
                                trace_id=state.get("trace_id", ""))
    dup_of = rt.seen.check_and_add(state["user_id"], job) if rt.seen else None
    if dup_of:
        return dict(job=job, status="skipped", decision=dict(action="skip", reasons=[f"duplicate of {dup_of}"], fit_score=0, risk_score=0),
                    steps=1, trace=[tr("scout", t, duplicate_of=dup_of)])
    return dict(job=job, status="running", steps=1, trace=[tr("scout", t, queued=job["job_id"])])
