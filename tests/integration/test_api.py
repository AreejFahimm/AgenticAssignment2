"""API-level tests: auth, tenant scoping, scan -> approval -> resume, SSE, analytics, degraded mode."""
import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.update(GIGSIM_INPROCESS="1", GIGSIM_ERROR_RATE="0", MEMORY_DB=":memory:", MODEL_PROFILE="offline", APP_DB=":memory:",
                  REVIEWER_PASSWORD="reviewer-pass-123", REVIEWER_PERSONA="fullstack_web_dev")

from fastapi.testclient import TestClient  # noqa: E402

pytestmark = pytest.mark.skipif(not (ROOT / "evals/datasets/dev_fullstack_web_dev.jsonl").exists(), reason="run data pipeline first")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    os.environ["CHECKPOINT_DB"] = str(tmp_path_factory.mktemp("ck") / "c.sqlite")
    from apps.api.main import app
    with TestClient(app) as c:
        yield c


def hdr(c, email, pw="password-123", persona="fullstack_web_dev"):
    r = c.post("/auth/register", json=dict(email=email, password=pw, persona=persona))
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def wait(c, h, pred, timeout=90):
    t = time.time()
    while time.time() - t < timeout:
        rows = c.get("/jobs", headers=h).json()
        hit = [r for r in rows if pred(r)]
        if hit:
            return hit[0]
        time.sleep(0.5)
    raise AssertionError(f"timeout; runs={[ (r['title'], r['status']) for r in c.get('/jobs', headers=h).json()]}")


def test_auth_and_reviewer_login(client):
    assert client.get("/me").status_code == 401
    r = client.post("/auth/login", json=dict(email="reviewer@gigbid.demo", password="reviewer-pass-123"))
    assert r.status_code == 200
    assert client.post("/auth/login", json=dict(email="reviewer@gigbid.demo", password="wrong-password")).status_code == 401
    me = client.get("/me", headers={"Authorization": f"Bearer {r.json()['token']}"}).json()
    assert me["persona"] == "fullstack_web_dev"


def test_full_flow_scan_approve_pipeline_analytics_and_tenant_isolation(client):
    h = hdr(client, "alice@example.com")
    assert client.put("/me/settings", headers=h, json=dict(weekly_connects_budget=100, saved_searches=[dict(name="web", query="react", interval_minutes=240)])).status_code == 200
    scan = client.post("/jobs/scan", headers=h).json()
    assert scan["queued"] > 0
    pending = wait(client, h, lambda r: r["status"] == "waiting_approval")
    tid = pending["thread_id"]
    # SSE shows node-by-node progress
    with client.stream("GET", f"/runs/{tid}/events", headers=h) as s:
        body = "".join(chunk for chunk in s.iter_text())
    assert "event: node" in body and "fit_matcher" in body and "event: interrupt" in body
    # a page refresh does not lose the pending approval
    assert any(a["thread_id"] == tid for a in client.get("/approvals", headers=h).json())
    p = client.get(f"/approvals/{tid}", headers=h).json()
    assert p["dry_run_preview"]["dry_run"] and p["evidence"] is not None and p["risk_report"] and p["price_quote"]
    studio = client.get(f"/proposals/{tid}", headers=h).json()
    assert studio["paragraphs"] and "compliance" in studio
    # tenant isolation: another user cannot see or approve it
    h2 = hdr(client, "bob@example.com")
    assert client.get(f"/approvals/{tid}", headers=h2).status_code == 404
    assert client.post(f"/approvals/{tid}", headers=h2, json=dict(status="approved")).status_code == 404
    assert client.get(f"/runs/{tid}/trace", headers=h2).status_code == 404
    # approve -> graph resumes -> submitted exactly once; second click is rejected
    assert client.post(f"/approvals/{tid}", headers=h, json=dict(status="approved")).status_code == 202
    done = wait(client, h, lambda r: r["thread_id"] == tid and r["status"] == "submitted")
    assert done["status"] == "submitted"
    assert client.post(f"/approvals/{tid}", headers=h, json=dict(status="approved")).status_code == 409
    tr = client.get(f"/runs/{tid}/trace", headers=h).json()
    assert tr["nodes"] and tr["trace_id"]
    pipe = client.get("/pipeline", headers=h).json()
    assert sum(len(v) for k, v in pipe.items() if k != "drafted") >= 1
    an = client.get("/analytics", headers=h).json()
    assert an["funnel"]["submitted"] >= 1 and "cost_latency" in an
    # reject with reason is recorded and surfaces in analytics
    other = wait(client, h, lambda r: r["status"] == "waiting_approval", timeout=120)
    assert client.post(f"/approvals/{other['thread_id']}", headers=h, json=dict(status="rejected", reason="too generic")).status_code == 202
    time.sleep(1.5)
    assert any(r["reason"] == "too generic" for r in client.get("/analytics", headers=h).json()["top_rejection_reasons"])


def test_validation_and_no_autosend_setting(client):
    h = hdr(client, "carol@example.com")
    assert client.put("/me/settings", headers=h, json=dict(autonomy="auto_send")).status_code == 422   # no such option exists
    assert client.post("/approvals/nope", headers=h, json=dict(status="edited")).status_code in (404, 422)
    assert client.post("/auth/register", json=dict(email="bad", password="short", persona="data_analyst")).status_code == 422


def test_degraded_mode_banner_queue_and_recovery(client):
    h = hdr(client, "dave@example.com")
    runner = client.app.state.runner
    from agent.mcp_client import MarketplaceDown
    real = runner.hub._once

    async def down(*a, **k):
        raise MarketplaceDown("connection refused")
    runner.hub._once = down
    runner.hub.backoff = 0
    try:
        client.put("/me/settings", headers=h, json=dict(saved_searches=[dict(name="x", query="react", interval_minutes=240)]))
        client.post("/jobs/scan", headers=h)
        st = client.get("/status", headers=h).json()
        assert st["marketplace_ok"] is False and "refused" in (st["marketplace_error"] or "")     # UI banner source
    finally:
        runner.hub._once = real
    # recovery: the marketplace is back -> probe clears the banner and re-drives the queued work
    st = client.post("/status/check", headers=h).json()
    assert st["marketplace_ok"] is True
    wait(client, h, lambda r: r["status"] in ("waiting_approval", "skipped", "running", "queued", "submitted", "watching"), timeout=120)
