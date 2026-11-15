"""GigSim-local: a small marketplace simulator written by the student because the instructor's
`gigsim/` was NOT in the starter kit. If the official GigSim arrives, point GIGSIM_BASE_URL at it and
write a new adapter mapping; do not edit the official one.

Features: jobs (from data/processed), client histories, Connects, proposal drafts/submit, messages,
per-token rate limit (429), occasional 5xx, simulated clients with HIDDEN preferences, and a
config-driven platform policy (platform_policy.json) so rule changes need no code edits.

Run:  uvicorn gigsim_local.app:app --port 8081
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = Path(os.getenv("GIGSIM_POLICY", Path(__file__).with_name("platform_policy.json")))
RATE_LIMIT = int(os.getenv("GIGSIM_RATE_LIMIT", "60"))          # requests / minute / token
ERROR_RATE = float(os.getenv("GIGSIM_ERROR_RATE", "0.02"))       # injected 503s
START_CONNECTS = int(os.getenv("GIGSIM_START_CONNECTS", "80"))

app = FastAPI(title="GigSim-local", version="0.1.0")


def load_policy() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def _load_jobs() -> dict[str, dict]:
    jobs: dict[str, dict] = {}
    for name in ("jobs.jsonl", "job_stream.jsonl"):
        p = ROOT / "data" / "processed" / name
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    j = json.loads(line)
                    jobs[j["job_id"]] = j
    for pat in ("dev_*.jsonl", "heldout_*.jsonl", "injection_set.jsonl"):  # evaluation jobs must exist in the marketplace
        for p in sorted((ROOT / "evals" / "datasets").glob(pat)):
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    j = json.loads(line)
                    j.pop("gold", None)  # labels never live in the marketplace
                    jobs[j["job_id"]] = j
    return jobs


JOBS = _load_jobs()
CLIENTS: dict[str, dict] = {}
PROPOSALS: dict[str, dict] = {}
MESSAGES: dict[str, list[dict]] = defaultdict(list)
BALANCES: dict[str, int] = {}
IDEMPOTENT: dict[str, dict] = {}
HITS: dict[str, deque] = defaultdict(deque)
_err = random.Random(4016)


def _client_for(job: dict) -> dict:
    cid = "client-" + hashlib.sha1(job["job_id"].encode()).hexdigest()[:8]
    if cid not in CLIENTS:
        r = random.Random(cid)
        planted = (job.get("planted") or {}).get("type") == "scam"
        CLIENTS[cid] = {
            "client_id": cid,
            "payment_verified": False if planted else r.random() > 0.15,
            "completed_projects": 0 if planted else r.randint(0, 40),
            "average_rating": 0.0 if planted else round(r.uniform(3.6, 5.0), 1),
            "total_spent_usd": 0 if planted else r.choice([0, 500, 2500, 10000, 50000]),
            "hire_rate": 0.0 if planted else round(r.uniform(0.1, 0.9), 2),
            "country": job.get("country"),
            "_hidden": {  # never exposed by the API
                "must_have": job["required_skills"],
                "budget_ceiling": (job["budget"].get("max") or 0) * 1.1,
                "dislikes_generic": r.random() < 0.8,
            },
        }
    return CLIENTS[cid]


def public_job(j: dict) -> dict:
    c = _client_for(j)
    pol = load_policy()
    out = {k: j[k] for k in ("job_id", "title", "description", "required_skills", "category", "budget",
                             "country", "posted_at") if k in j}
    out["client_id"] = c["client_id"]
    out["connects_cost"] = connects_cost(j, pol)
    return out


def connects_cost(j: dict, pol: dict) -> int:
    base = pol["connects_cost_per_proposal"]
    b = j["budget"]
    top = b.get("max") or b.get("min") or 0
    if top >= pol.get("premium_budget_threshold", 10**9):
        base += pol.get("premium_job_extra_connects", 0)
    return base


def user(authorization: str = Header(default="")) -> str:
    if not authorization.startswith("Bearer ") or len(authorization) < 12:
        raise HTTPException(401, "missing or invalid bearer token")
    uid = authorization[7:]
    now = time.time()
    q = HITS[uid]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        raise HTTPException(429, "rate limit exceeded", headers={"Retry-After": "5"})
    q.append(now)
    if _err.random() < ERROR_RATE:
        raise HTTPException(503, "simulated upstream error")
    BALANCES.setdefault(uid, START_CONNECTS)
    return uid


@app.get("/health")
def health():
    return {"status": "ok", "service": "gigsim-local", "jobs": len(JOBS)}


@app.get("/policy")
def policy():
    return load_policy()


@app.get("/jobs")
def list_jobs(q: str = "", limit: int = Query(20, le=100), offset: int = 0, uid: str = Depends(user)):
    ql = q.lower()
    hits = [j for j in JOBS.values() if not ql or ql in (j["title"] + " " + j["description"]).lower()]
    return {"total": len(hits), "jobs": [public_job(j) for j in hits[offset: offset + limit]]}


@app.get("/jobs/{job_id}")
def get_job(job_id: str, uid: str = Depends(user)):
    if job_id not in JOBS:
        raise HTTPException(404, "job not found")
    return public_job(JOBS[job_id])


@app.get("/clients/{client_id}/history")
def client_history(client_id: str, uid: str = Depends(user)):
    if client_id not in CLIENTS:
        raise HTTPException(404, "client not found")
    return {k: v for k, v in CLIENTS[client_id].items() if not k.startswith("_")}


@app.get("/connects/balance")
def balance(uid: str = Depends(user)):
    return {"user": uid, "balance": BALANCES[uid]}


class DraftIn(BaseModel):
    job_id: str
    cover_letter: str = Field(min_length=1, max_length=6000)
    screening_answers: list[str] = Field(default_factory=list)
    bid_amount: float = Field(gt=0)
    idempotency_key: str = Field(min_length=8)


@app.post("/proposals")
def create_draft(body: DraftIn, uid: str = Depends(user)):
    if (uid, body.idempotency_key) in IDEMPOTENT:
        return IDEMPOTENT[(uid, body.idempotency_key)]
    if body.job_id not in JOBS:
        raise HTTPException(404, "job not found")
    pol = load_policy()
    if len(body.cover_letter) < pol.get("min_cover_letter_chars", 0):
        raise HTTPException(422, f"cover letter shorter than {pol['min_cover_letter_chars']} chars (platform policy)")
    pid = "prop-" + hashlib.sha1(f"{uid}|{body.idempotency_key}".encode()).hexdigest()[:10]   # deterministic: simulated replies are reproducible
    PROPOSALS[pid] = {"proposal_id": pid, "user": uid, "status": "draft", **body.model_dump(exclude={"idempotency_key"}),
                      "connects_cost": connects_cost(JOBS[body.job_id], pol)}
    IDEMPOTENT[(uid, body.idempotency_key)] = PROPOSALS[pid]
    return PROPOSALS[pid]


class SubmitIn(BaseModel):
    idempotency_key: str = Field(min_length=8)


@app.post("/proposals/{pid}/submit")
def submit(pid: str, body: SubmitIn, uid: str = Depends(user)):
    if (uid, body.idempotency_key) in IDEMPOTENT:
        return IDEMPOTENT[(uid, body.idempotency_key)]
    p = PROPOSALS.get(pid)
    if not p or p["user"] != uid:
        raise HTTPException(404, "proposal not found")
    if p["status"] != "draft":
        raise HTTPException(409, f"proposal already {p['status']}")
    pol = load_policy()
    today = sum(1 for x in PROPOSALS.values() if x["user"] == uid and x["status"] != "draft")
    if today >= pol.get("max_proposals_per_day", 10**6):
        raise HTTPException(429, "daily proposal limit reached (platform policy)")
    if BALANCES[uid] < p["connects_cost"]:
        raise HTTPException(402, "insufficient Connects")
    BALANCES[uid] -= p["connects_cost"]
    p["status"] = "submitted"
    _simulate_client(p)
    IDEMPOTENT[(uid, body.idempotency_key)] = p
    return p


GENERIC = ("hard-working", "please hire me", "i can do this job", "dear sir")


def _simulate_client(p: dict) -> None:
    job = JOBS[p["job_id"]]
    c = _client_for(job)
    hid = c["_hidden"]
    text = p["cover_letter"].lower()
    skill_hits = sum(1 for s in hid["must_have"] if s.lower() in text) / max(len(hid["must_have"]), 1)
    generic = any(g in text for g in GENERIC) or len(text) < 200
    over = p["bid_amount"] > hid["budget_ceiling"] > 0
    score = 0.15 + 0.5 * skill_hits - (0.25 if (generic and hid["dislikes_generic"]) else 0) - (0.2 if over else 0)
    score += 0.1 if c["payment_verified"] else -0.1
    r = random.Random(p["proposal_id"] + "sim")
    u = r.random()
    p["status_detail"] = {"viewed": u < 0.8}
    if (job.get("planted") or {}).get("type") == "scam":
        return
    if u < max(score, 0):
        p["status"] = "replied"
        MESSAGES[p["proposal_id"]].append({"from": "client", "text": "Thanks for the proposal. Can you share more on your approach and timeline?"})
        if r.random() < score * 0.6:
            p["status"] = "interview"
            MESSAGES[p["proposal_id"]].append({"from": "client", "text": "We would like a short call. What times work this week?"})
            if r.random() < score * 0.5:
                p["status"] = "hired"


@app.get("/proposals/{pid}")
def get_proposal(pid: str, uid: str = Depends(user)):
    p = PROPOSALS.get(pid)
    if not p or p["user"] != uid:
        raise HTTPException(404, "proposal not found")
    return p


@app.get("/proposals")
def list_proposals(uid: str = Depends(user)):
    return [p for p in PROPOSALS.values() if p["user"] == uid]


@app.get("/messages")
def list_messages(proposal_id: str, uid: str = Depends(user)):
    return MESSAGES.get(proposal_id, [])


class MsgIn(BaseModel):
    proposal_id: str
    text: str = Field(min_length=1, max_length=4000)
    idempotency_key: str = Field(min_length=8)


@app.post("/messages")
def send_message(body: MsgIn, uid: str = Depends(user)):
    if (uid, body.idempotency_key) in IDEMPOTENT:
        return IDEMPOTENT[(uid, body.idempotency_key)]
    MESSAGES[body.proposal_id].append({"from": "freelancer", "text": body.text})
    out = {"ok": True, "n_messages": len(MESSAGES[body.proposal_id])}
    IDEMPOTENT[(uid, body.idempotency_key)] = out
    return out
