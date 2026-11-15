"""Outcome evaluation (B4): GigSim simulated reply / interview / hire rate on a FIXED job set, per retrieval variant.

    python -m evals.runners.gigsim_outcomes [--per-persona 25] [--variants v0 v2 best]

The human is SIMULATED by auto-approving (evaluation only; the product never auto-sends). Each variant gets its own
fresh GigSim user so Connects and state never leak between arms. A `generic` control arm submits a template letter
that cites no evidence, to show whether grounding matters to the simulated clients. Replies are deterministic per
proposal id in GigSim-local (seeded), so differences come from the letter, not from luck of the draw.
Results: evals/results/outcomes.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time

from evals.runners._harness import PERSONAS, ROOT, Harness, dev, pct

GENERIC = "Hello, I am a hard-working professional and I can do this job. Please hire me."


async def arm(variant: str, per_persona: int) -> dict:
    from mcp_servers.portfolio import tools
    tools.VARIANT = variant if variant != "generic" else "best"
    h = Harness()
    n = replied = interview = hired = connects = 0
    lat = []
    by_persona = {}
    for persona in PERSONAS:
        rows = [r for r in dev(persona, "dev") if r["gold"]["decision"] == "bid"][:per_persona]   # FIXED set: first N gold-bid jobs
        pn = pr = 0
        for r in rows:
            user = f"out-{variant}-{persona}"
            t = time.time()
            if variant == "generic":
                out = await _generic(h, persona, r["job_id"], user)
            else:
                out = await h.run(persona, r["job_id"], user=user, approve=True)
            lat.append(time.time() - t)
            st = out["state"]
            sub = st.get("submission")
            if not sub:
                continue
            n += 1
            pn += 1
            status = sub["status"]
            connects += sub["connects_cost"]
            replied += status in ("replied", "interview", "hired")
            interview += status in ("interview", "hired")
            hired += status == "hired"
            pr += status in ("replied", "interview", "hired")
        by_persona[persona] = dict(submitted=pn, reply_rate=round(pr / pn, 4) if pn else None)
    return dict(variant=variant, submitted=n, reply_rate=round(replied / n, 4) if n else None, interview_rate=round(interview / n, 4) if n else None,
                hire_rate=round(hired / n, 4) if n else None, connects_spent=connects, p95_latency_s=pct(lat, .95), by_persona=by_persona)


async def _generic(h: Harness, persona: str, job_id: str, user: str) -> dict:
    """Control arm: bypass the writer, submit the generic letter at the same price via the same approved path."""
    from agent.mcp_client import MCPHub
    hub = MCPHub()
    draft = await hub.call("submitter", "marketplace.create_proposal_draft", dict(job_id=job_id, cover_letter=GENERIC, bid_amount=100.0,
                           idempotency_key=f"{user}.{job_id}:draft"), user=user)
    sub = await hub.call("submitter", "marketplace.submit_proposal", dict(proposal_id=draft["proposal_id"], idempotency_key=f"{user}.{job_id}:submit"), user=user)
    return dict(state=dict(submission=dict(proposal_id=draft["proposal_id"], status=sub["status"], connects_cost=draft["connects_cost"])))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-persona", type=int, default=25)
    ap.add_argument("--variants", nargs="*", default=["generic", "v0", "v2", "best", "ship"])
    a = ap.parse_args()

    async def main():
        out = []
        for v in a.variants:
            r = await arm(v, a.per_persona)
            print(r, flush=True)
            out.append(r)
        return out
    res = asyncio.run(main())
    (ROOT / "evals" / "results").mkdir(parents=True, exist_ok=True)
    (ROOT / "evals" / "results" / "outcomes.json").write_text(json.dumps(dict(arms=res, per_persona_target=a.per_persona,
                                                                             note="simulated human approval (eval only); GigSim-local clients are rule-based"), indent=2), encoding="utf-8")
