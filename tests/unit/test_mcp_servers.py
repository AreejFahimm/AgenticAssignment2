"""Unit tests for the three MCP servers through an in-memory MCP client (A7)."""
import json
import os
import sys
from pathlib import Path

import httpx
import pytest
from mcp.shared.memory import create_connected_server_and_client_session as connect

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ["GIGSIM_ERROR_RATE"] = "0"
os.environ.setdefault("AUDIT_LOG", str(ROOT / "data" / "processed" / "audit_test.jsonl"))

from agent.marketplace_port import GigSimAdapter  # noqa: E402
from gigsim_local.app import app as gigsim_app  # noqa: E402
from mcp_servers.marketplace import server as market  # noqa: E402
from mcp_servers.portfolio import server as portfolio  # noqa: E402
from mcp_servers.workspace import server as workspace  # noqa: E402

pytestmark = pytest.mark.skipif(not (ROOT / "data/processed/jobs.jsonl").exists(), reason="run the data pipeline first")


def payload(res):
    return res.structuredContent if res.structuredContent is not None else json.loads(res.content[0].text)


@pytest.fixture(autouse=True)
def _market_port(tmp_path, monkeypatch):
    market.AUDIT_PATH = tmp_path / "audit.jsonl"
    market._idem.clear()
    market._hits.clear()
    market.set_port_factory(lambda user: GigSimAdapter("http://gigsim", f"user-{user}-token", backoff=0.0,
                                                       transport=httpx.ASGITransport(app=gigsim_app)))
    monkeypatch.setattr(workspace, "STORE", tmp_path / "ws")


# ---------- portfolio ----------
async def test_portfolio_tools_resources_prompts():
    portfolio.PERSONA = "ai_ml_engineer"
    async with connect(portfolio.mcp._mcp_server) as c:
        tools = {t.name: t for t in (await c.list_tools()).tools}
        assert set(tools) == {"search_evidence", "get_case_study", "list_skills"}
        assert all(t.annotations.readOnlyHint for t in tools.values())
        res = payload(await c.call_tool("search_evidence", {"requirement": "text classification with scikit-learn", "k": 3}))
        assert res["items"] and all("evidence_id" in i and "outcome" in i and "source" in i for i in res["items"])
        cs = res["items"][0]["source"]
        assert (await c.read_resource(f"portfolio://case/{cs}")).contents
        prompts = [p.name for p in (await c.list_prompts()).prompts]
        assert "answer_screening_question" in prompts
        bad = await c.call_tool("search_evidence", {"requirement": "x", "k": 99})
        assert bad.isError  # schema/constraint enforced
        trav = await c.call_tool("get_case_study", {"id": "../profile"})
        assert trav.isError  # path traversal blocked


# ---------- marketplace ----------
async def _a_job(c):
    return payload(await c.call_tool("search_jobs", {"limit": 1}))["jobs"][0]


async def test_marketplace_annotations_and_reads():
    async with connect(market.mcp._mcp_server) as c:
        tools = {t.name: t for t in (await c.list_tools()).tools}
        assert tools["search_jobs"].annotations.readOnlyHint is True
        assert tools["submit_proposal"].annotations.destructiveHint is True
        assert tools["submit_proposal"].annotations.idempotentHint is True
        assert tools["create_proposal_draft"].annotations.readOnlyHint is False
        job = await _a_job(c)
        hist = payload(await c.call_tool("get_client_history", {"client_id": job["client_id"]}))
        assert "payment_verified" in hist and "_hidden" not in json.dumps(hist)


async def test_dry_run_spends_nothing_and_idempotent_submit():
    async with connect(market.mcp._mcp_server) as c:
        job = await _a_job(c)
        bal0 = payload(await c.call_tool("get_connects_balance", {}))["balance"]
        args = dict(job_id=job["job_id"], cover_letter="I built a churn model. " * 20, bid_amount=120, idempotency_key="draft-key-0001")
        prev = payload(await c.call_tool("create_proposal_draft", dict(args, dry_run=True)))
        assert prev["dry_run"] and prev["proposal_id"] is None and prev["connects_cost"] == job["connects_cost"]
        d1 = payload(await c.call_tool("create_proposal_draft", args))
        d2 = payload(await c.call_tool("create_proposal_draft", args))
        assert d1["proposal_id"] == d2["proposal_id"]
        sub_prev = payload(await c.call_tool("submit_proposal", dict(proposal_id=d1["proposal_id"], idempotency_key="submit-key-01", dry_run=True)))
        assert sub_prev["balance_after"] == bal0 - job["connects_cost"]
        assert payload(await c.call_tool("get_connects_balance", {}))["balance"] == bal0  # dry runs are free
        for _ in range(3):  # retried 3x -> charged once
            await c.call_tool("submit_proposal", dict(proposal_id=d1["proposal_id"], idempotency_key="submit-key-01"))
        assert payload(await c.call_tool("get_connects_balance", {}))["balance"] == bal0 - job["connects_cost"]


async def test_input_constraints_and_audit_log_masks_pii():
    async with connect(market.mcp._mcp_server) as c:
        job = await _a_job(c)
        bad = await c.call_tool("create_proposal_draft", dict(job_id=job["job_id"], cover_letter="hi", bid_amount=-5, idempotency_key="draft-key-0002"))
        assert bad.isError
        short = await c.call_tool("create_proposal_draft", dict(job_id=job["job_id"], cover_letter="hi", bid_amount=5, idempotency_key="x"))
        assert short.isError  # idempotency key too short
        await c.call_tool("send_message", dict(proposal_id="p", text="mail me at a.b@example.com", idempotency_key="msg-key-0001", dry_run=True))
    log = market.AUDIT_PATH.read_text(encoding="utf-8")
    assert "a.b@example.com" not in log and "[EMAIL]" in log
    rec = json.loads(log.splitlines()[0])
    assert {"user", "tool", "args", "trace_id", "ts"} <= set(rec)


async def test_rate_limiter(monkeypatch):
    monkeypatch.setattr(market, "RATE_LIMIT_PER_MIN", 3)
    async with connect(market.mcp._mcp_server) as c:
        results = [await c.call_tool("get_connects_balance", {}) for _ in range(5)]
    assert any(r.isError for r in results)


async def test_degraded_mode_error_is_explicit(monkeypatch):
    class Dead:
        async def search_jobs(self, *a, **k):
            from agent.marketplace_port import MarketplaceUnavailable
            raise MarketplaceUnavailable("connection refused")
    market.set_port_factory(lambda u: Dead())
    async with connect(market.mcp._mcp_server) as c:
        r = await c.call_tool("search_jobs", {})
        assert r.isError and "MARKETPLACE_UNAVAILABLE" in r.content[0].text


# ---------- workspace ----------
async def test_workspace_tools_idempotent():
    async with connect(workspace.mcp._mcp_server) as c:
        slots = payload(await c.call_tool("free_calendar_slots", {"days": 3, "from_iso": "2026-11-16T08:00"}))["slots"]
        assert slots
        h1 = payload(await c.call_tool("create_tentative_hold", {"start_iso": slots[0]["start"], "title": "Interview", "idempotency_key": "hold-key-0001"}))
        h2 = payload(await c.call_tool("create_tentative_hold", {"start_iso": slots[0]["start"], "title": "Interview", "idempotency_key": "hold-key-0001"}))
        assert h1["hold_id"] == h2["hold_id"] and h1["status"] == "tentative"
        again = payload(await c.call_tool("free_calendar_slots", {"days": 3, "from_iso": "2026-11-16T08:00"}))["slots"]
        assert slots[0]["start"] not in [s["start"] for s in again]  # hold removes the slot
        d = payload(await c.call_tool("create_email_draft", {"to": "client@example.com", "subject": "Re: job", "body": "Thanks"}))
        assert d["status"] == "draft"
        bad = await c.call_tool("create_email_draft", {"to": "not-an-email", "subject": "s", "body": "b"})
        assert bad.isError
