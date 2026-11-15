"""Integration test: GigSimAdapter against the in-process GigSim-local app (no network)."""
import os
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ["GIGSIM_ERROR_RATE"] = "0"

from agent.marketplace_port import GigSimAdapter, MarketplaceRejected, make_marketplace  # noqa: E402
from gigsim_local.app import app  # noqa: E402

pytestmark = pytest.mark.skipif(not (ROOT / "data/processed/jobs.jsonl").exists(),
                                reason="run scripts/preprocess_jobs.py first")


def adapter(token="test-user-0001"):
    return GigSimAdapter("http://gigsim", token, backoff=0.0, transport=httpx.ASGITransport(app=app))


async def _first_job(a):
    jobs = await a.search_jobs("", limit=1)
    return jobs[0]


@pytest.mark.asyncio
async def test_read_tools():
    a = adapter()
    job = await _first_job(a)
    assert job["connects_cost"] > 0
    assert (await a.get_job(job["job_id"]))["job_id"] == job["job_id"]
    hist = await a.get_client_history(job["client_id"])
    assert "_hidden" not in hist and "payment_verified" in hist  # hidden prefs never leak
    assert (await a.get_connects_balance())["balance"] > 0


@pytest.mark.asyncio
async def test_submit_is_idempotent_and_spends_connects_once():
    a = adapter("test-user-0002")
    job = await _first_job(a)
    before = (await a.get_connects_balance())["balance"]
    draft = await a.create_proposal_draft(
        {"job_id": job["job_id"], "cover_letter": "x" * 300, "bid_amount": 100.0}, "draft-key-0001")
    again = await a.create_proposal_draft(
        {"job_id": job["job_id"], "cover_letter": "x" * 300, "bid_amount": 100.0}, "draft-key-0001")
    assert draft["proposal_id"] == again["proposal_id"]
    await a.submit_proposal(draft["proposal_id"], "submit-key-0001")
    await a.submit_proposal(draft["proposal_id"], "submit-key-0001")  # retry with same key
    after = (await a.get_connects_balance())["balance"]
    assert before - after == job["connects_cost"]  # charged exactly once


@pytest.mark.asyncio
async def test_rejections_surface_as_typed_errors():
    a = adapter("test-user-0003")
    with pytest.raises(MarketplaceRejected) as e:
        await a.get_job("does-not-exist")
    assert e.value.status == 404


def test_factory_uses_config_mode():
    m = make_marketplace({"marketplace": {"mode": "gigsim"}}, base_url="http://x", token="t" * 12)
    assert isinstance(m, GigSimAdapter)
