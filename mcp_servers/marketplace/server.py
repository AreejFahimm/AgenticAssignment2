"""Marketplace MCP server (A2). Wraps the ONE marketplace port (GigSim or live Upwork, chosen by config).

Guarantees: Pydantic input schemas with constraints, declared output schemas, tool annotations,
idempotency key on every write, dry_run preview, bearer-token auth on the HTTP endpoint,
per-user rate limiter below GigSim's limit, append-only audit log with trace id.

Run:  python -m mcp_servers.marketplace.server --http --port 9102
Env:  MARKETPLACE_MCP_TOKENS="tokenA:alice,tokenB:bob"  GIGSIM_BASE_URL=http://localhost:8081
"""
from __future__ import annotations

import argparse
import contextvars
import json
import os
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from agent.marketplace_port import MarketplacePort, MarketplaceRejected, MarketplaceUnavailable, make_marketplace
from agent.security import mask_pii

AUDIT_PATH = Path(os.getenv("AUDIT_LOG", Path(__file__).resolve().parents[2] / "data" / "processed" / "audit.jsonl"))
RATE_LIMIT_PER_MIN = int(os.getenv("MCP_RATE_LIMIT", "40"))  # GigSim allows 60
current_user: contextvars.ContextVar[str] = contextvars.ContextVar("current_user", default="local-user")
current_trace: contextvars.ContextVar[str] = contextvars.ContextVar("current_trace", default="")

mcp = FastMCP("gigbid-marketplace", instructions="Marketplace access. Writes accept dry_run=true to preview. "
              "Never call a write tool without explicit human approval upstream.")
_ports: dict[str, MarketplacePort] = {}
_port_factory = None  # tests inject a factory returning a MarketplacePort
_hits: dict[str, deque] = defaultdict(deque)
_idem: dict[str, Any] = {}

READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)
DRAFT = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True)
SPEND = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True)


def set_port_factory(f) -> None:
    global _port_factory
    _port_factory = f
    _ports.clear()


def port() -> MarketplacePort:
    user = current_user.get()
    if user not in _ports:
        if _port_factory:
            _ports[user] = _port_factory(user)
        elif os.getenv("GIGSIM_INPROCESS") == "1":  # single-process deploy: GigSim-local mounted in memory
            import httpx

            from agent.marketplace_port import GigSimAdapter
            from gigsim_local.app import app as gigsim_app
            _ports[user] = GigSimAdapter("http://gigsim", f"user-{user}-token", transport=httpx.ASGITransport(app=gigsim_app))
        else:
            _ports[user] = make_marketplace({"marketplace": {"mode": os.getenv("MARKETPLACE_MODE", "gigsim")}},
                                            base_url=os.getenv("GIGSIM_BASE_URL", "http://localhost:8081"),
                                            token=os.getenv("GIGSIM_API_TOKEN", f"user-{user}-token"))
    return _ports[user]


def audit(tool: str, args: dict, result: Any, ok: bool) -> None:
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    rec = dict(ts=time.time(), user=current_user.get(), tool=tool, trace_id=current_trace.get() or uuid.uuid4().hex[:12],
               args=json.loads(mask_pii(json.dumps(args, default=str))), result=json.loads(mask_pii(json.dumps(result, default=str)))
               if ok else str(result)[:300], ok=ok)
    with AUDIT_PATH.open("a", encoding="utf-8") as f:  # append-only
        f.write(json.dumps(rec) + "\n")


def _limit() -> None:
    q, now = _hits[current_user.get()], time.time()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_LIMIT_PER_MIN:
        raise RuntimeError(f"rate limit: {RATE_LIMIT_PER_MIN}/min per user")
    q.append(now)


async def _call(tool: str, args: dict, coro_fn):
    _limit()
    try:
        res = await coro_fn()
    except MarketplaceUnavailable as e:
        audit(tool, args, e, False)
        raise RuntimeError(f"MARKETPLACE_UNAVAILABLE: {e}") from e
    except MarketplaceRejected as e:
        audit(tool, args, e, False)
        raise RuntimeError(f"MARKETPLACE_REJECTED: {e}") from e
    audit(tool, args, res, True)
    return res


# ---------- schemas ----------
class JobSummary(BaseModel):
    job_id: str
    title: str
    description: str = ""
    required_skills: list[str] = Field(default_factory=list)
    category: str | None = None
    budget: dict[str, Any] = Field(default_factory=dict)
    client_id: str | None = None
    connects_cost: int | None = None


class JobList(BaseModel):
    jobs: list[JobSummary]


class ClientHistory(BaseModel):
    client_id: str
    payment_verified: bool
    completed_projects: int
    average_rating: float
    total_spent_usd: float
    hire_rate: float
    country: str | None = None


class Balance(BaseModel):
    user: str
    balance: int


class MessageList(BaseModel):
    messages: list[dict[str, Any]]


class ProposalList(BaseModel):
    proposals: list[dict[str, Any]]


class PolicyOut(BaseModel):
    policy: dict[str, Any]


class ProposalDraftOut(BaseModel):
    dry_run: bool
    proposal_id: str | None = None
    status: str
    preview: dict[str, Any]
    connects_cost: int
    idempotency_key: str


class SubmitOut(BaseModel):
    dry_run: bool
    proposal_id: str
    status: str
    connects_cost: int
    balance_after: int | None = None
    idempotency_key: str


class MessageOut(BaseModel):
    dry_run: bool
    sent: bool
    preview: dict[str, Any]
    idempotency_key: str


IdemKey = Annotated[str, Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$",
                               description="Unique per logical action; a retry with the same key never repeats the effect.")]


# ---------- read tools ----------
@mcp.tool(annotations=READ, description="Search marketplace jobs by free-text query.")
async def search_jobs(query: str = "", limit: Annotated[int, Field(ge=1, le=50)] = 20) -> JobList:
    jobs = await _call("search_jobs", dict(query=query, limit=limit), lambda: port().search_jobs(query, limit))
    return JobList(jobs=[JobSummary(**{k: v for k, v in j.items() if k in JobSummary.model_fields}) for j in jobs])


@mcp.tool(annotations=READ, description="Get one job by id.")
async def get_job(job_id: str) -> JobSummary:
    j = await _call("get_job", dict(job_id=job_id), lambda: port().get_job(job_id))
    return JobSummary(**{k: v for k, v in j.items() if k in JobSummary.model_fields})


@mcp.tool(annotations=READ, description="Get a client's history: verification, rating, spend and hire rate.")
async def get_client_history(client_id: str) -> ClientHistory:
    return ClientHistory(**await _call("get_client_history", dict(client_id=client_id), lambda: port().get_client_history(client_id)))


@mcp.tool(annotations=READ, description="Get the user's Connects balance.")
async def get_connects_balance() -> Balance:
    return Balance(**await _call("get_connects_balance", {}, lambda: port().get_connects_balance()))


@mcp.tool(annotations=READ, description="List messages on a proposal thread.")
async def list_messages(proposal_id: str) -> MessageList:
    return MessageList(messages=await _call("list_messages", dict(proposal_id=proposal_id), lambda: port().list_messages(proposal_id)))


@mcp.tool(annotations=READ, description="List the user's proposals with their current status (viewed, replied, interview, hired...).")
async def list_proposals() -> ProposalList:
    return ProposalList(proposals=await _call("list_proposals", {}, lambda: port().list_proposals()))


@mcp.tool(annotations=READ, description="Get the marketplace's current platform policy (Connects cost, minimum cover letter length, daily limits).")
async def get_platform_policy() -> PolicyOut:
    return PolicyOut(policy=await _call("get_platform_policy", {}, lambda: port().get_platform_policy()))


# ---------- write tools ----------
@mcp.tool(annotations=DRAFT, description="Create a proposal DRAFT (does not spend Connects). dry_run=true returns exactly what would be sent.")
async def create_proposal_draft(
    job_id: str,
    cover_letter: Annotated[str, Field(min_length=1, max_length=6000)],
    bid_amount: Annotated[float, Field(gt=0, le=1_000_000)],
    idempotency_key: IdemKey,
    screening_answers: list[str] | None = None,
    dry_run: bool = False,
) -> ProposalDraftOut:
    payload = dict(job_id=job_id, cover_letter=cover_letter, bid_amount=bid_amount, screening_answers=screening_answers or [])
    job = await _call("get_job", dict(job_id=job_id), lambda: port().get_job(job_id))
    cost = int(job.get("connects_cost") or 0)
    if dry_run:
        audit("create_proposal_draft", dict(payload, dry_run=True), "preview", True)
        return ProposalDraftOut(dry_run=True, status="preview", preview=payload, connects_cost=cost, idempotency_key=idempotency_key)
    if idempotency_key in _idem:
        return _idem[idempotency_key]
    res = await _call("create_proposal_draft", dict(payload, idempotency_key=idempotency_key),
                      lambda: port().create_proposal_draft(payload, idempotency_key))
    out = ProposalDraftOut(dry_run=False, proposal_id=res["proposal_id"], status=res["status"], preview=payload,
                           connects_cost=int(res.get("connects_cost", cost)), idempotency_key=idempotency_key)
    _idem[idempotency_key] = out
    return out


@mcp.tool(annotations=SPEND, description="SUBMIT a draft proposal and spend Connects. Requires prior human approval. dry_run=true previews cost and balance.")
async def submit_proposal(proposal_id: str, idempotency_key: IdemKey, dry_run: bool = False) -> SubmitOut:
    prop = await _call("get_proposal", dict(proposal_id=proposal_id), lambda: port().get_proposal(proposal_id))
    bal = (await _call("get_connects_balance", {}, lambda: port().get_connects_balance()))["balance"]
    cost = int(prop.get("connects_cost", 0))
    if dry_run:
        audit("submit_proposal", dict(proposal_id=proposal_id, dry_run=True), "preview", True)
        return SubmitOut(dry_run=True, proposal_id=proposal_id, status="preview", connects_cost=cost, balance_after=bal - cost,
                         idempotency_key=idempotency_key)
    if idempotency_key in _idem:
        return _idem[idempotency_key]
    res = await _call("submit_proposal", dict(proposal_id=proposal_id, idempotency_key=idempotency_key),
                      lambda: port().submit_proposal(proposal_id, idempotency_key))
    out = SubmitOut(dry_run=False, proposal_id=proposal_id, status=res["status"], connects_cost=cost, balance_after=None,
                    idempotency_key=idempotency_key)
    _idem[idempotency_key] = out
    return out


@mcp.tool(annotations=SPEND, description="SEND a message to a client. Requires prior human approval. dry_run=true previews.")
async def send_message(proposal_id: str, text: Annotated[str, Field(min_length=1, max_length=4000)], idempotency_key: IdemKey,
                       dry_run: bool = False) -> MessageOut:
    preview = dict(proposal_id=proposal_id, text=text)
    if dry_run:
        audit("send_message", dict(preview, dry_run=True), "preview", True)
        return MessageOut(dry_run=True, sent=False, preview=preview, idempotency_key=idempotency_key)
    if idempotency_key in _idem:
        return _idem[idempotency_key]
    await _call("send_message", dict(preview, idempotency_key=idempotency_key), lambda: port().send_message(proposal_id, text, idempotency_key))
    out = MessageOut(dry_run=False, sent=True, preview=preview, idempotency_key=idempotency_key)
    _idem[idempotency_key] = out
    return out


# ---------- HTTP auth (bearer) ----------
class BearerAuth:
    """ASGI middleware: Authorization: Bearer <token> -> user; also propagates x-trace-id."""

    def __init__(self, app, tokens: dict[str, str]):
        self.app, self.tokens = app, tokens

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
        tok = headers.get("authorization", "").removeprefix("Bearer ").strip()
        if tok not in self.tokens:
            await send({"type": "http.response.start", "status": 401, "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": b'{"error":"unauthorized"}'})
            return
        current_user.set(self.tokens[tok])
        current_trace.set(headers.get("x-trace-id", uuid.uuid4().hex[:12]))
        await self.app(scope, receive, send)


def http_app():
    tokens = dict(p.split(":", 1) for p in os.environ["MARKETPLACE_MCP_TOKENS"].split(",") if p)
    return BearerAuth(mcp.streamable_http_app(), tokens)


if __name__ == "__main__":
    import uvicorn
    ap = argparse.ArgumentParser()
    ap.add_argument("--http", action="store_true")
    ap.add_argument("--port", type=int, default=9102)
    a = ap.parse_args()
    if a.http:
        uvicorn.run(http_app(), host="0.0.0.0", port=a.port)
    else:
        mcp.run()
