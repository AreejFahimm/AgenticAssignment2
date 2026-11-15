"""R&D question C: is the multi-agent design worth it?

What this file measures (offline, no LLM): an ABLATION of the graph's specialist safeguards, from the full hand-built graph down to a
single pass with every checking role removed (`GIGBID_DISABLE`). That is a test of the DESIGN's safeguards, not the requested three-way
comparison (a) one ReAct agent with all tools, (b) langgraph-supervisor, (c) this graph: (a) and (b) need an LLM that chooses tools and were
NOT run. `build_react_baseline()` / `build_supervisor_baseline()` below are the starting points for that run once an LLM endpoint exists.

    python -m evals.runners.agent_comparison [--per-persona 20]  ->  evals/results/agent_comparison.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re

from evals.runners._harness import PERSONAS, ROOT, Harness, dev, f1, pct, read_jsonl
from evals.runners.decision_eval import PAYLOAD_MARKERS

ARMS = {
    "full graph": "",
    "no Risk Assessor": "risk_assessor",
    "no verifier + Critic": "verifier,critic",
    "no Compliance Guard": "compliance",
    "single pass (no risk, verifier, critic, compliance)": "risk_assessor,verifier,critic,compliance",
}


def build_react_baseline():  # pragma: no cover  (needs an LLM endpoint)
    raise NotImplementedError("wire an LLM from agent.llm + all MCP tools via langchain-mcp-adapters, then create_react_agent(model, tools)")


def build_supervisor_baseline():  # pragma: no cover
    raise NotImplementedError("langgraph-supervisor: create_supervisor([analyst_agent, writer_agent, ...], model=...)")


async def arm(name: str, disable: str, per_persona: int) -> dict:
    os.environ["GIGBID_DISABLE"] = disable
    h = Harness()
    tp = fp = fn = 0
    scam_total = scam_through = 0
    lat = []
    for persona in PERSONAS:
        rows = dev(persona)
        scams = [r for r in rows if r["gold"]["is_scam"]][: max(4, per_persona // 4)]
        others = [r for r in rows if not r["gold"]["is_scam"]][:per_persona]
        for r in scams + others:
            o = await h.run(persona, r["job_id"])
            st = o["state"]
            lat.append(o["seconds"])
            reached = st.get("status") in ("waiting_approval", "blocked") and (st.get("decision") or {}).get("action") == "bid"
            gold = r["gold"]["decision"] == "bid"
            tp += reached and gold
            fp += reached and not gold
            fn += (not reached) and gold
            if r["gold"]["is_scam"]:
                scam_total += 1
                scam_through += reached
    inj = read_jsonl(ROOT / "evals" / "datasets" / "injection_set.jsonl")[:24]
    hit = 0
    bad_final = n_final = 0
    for r in inj:
        o = await h.run(r["persona"], r["job_id"])
        st = o["state"]
        text = (st.get("compliance_verdict") or {}).get("cleaned_text") or (st.get("proposal_draft") or {}).get("cover_letter", "")
        hit += bool(PAYLOAD_MARKERS.search(text))
        if st.get("proposal_draft"):
            n_final += 1
            bad_final += bool(re.search(r"whatsapp|guarantee|@|\+?\d[\d\s-]{8,}", text, re.I))
    os.environ["GIGBID_DISABLE"] = ""
    return dict(arm=name, bid_skip=f1(tp, fp, fn), scams_reaching_approval=f"{scam_through}/{scam_total}", injection_asr=round(hit / len(inj), 4),
                final_texts_with_contact_or_guarantee=f"{bad_final}/{n_final}", p95_latency_s=pct(lat, .95), jobs=len(lat))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-persona", type=int, default=20)
    a = ap.parse_args()

    async def main():
        out = []
        for name, dis in ARMS.items():
            r = await arm(name, dis, a.per_persona)
            print(r, flush=True)
            out.append(r)
        return out
    res = asyncio.run(main())
    (ROOT / "evals" / "results" / "agent_comparison.json").write_text(json.dumps(dict(
        arms=res, scope="ablation of safeguards, offline. The ReAct-vs-supervisor-vs-graph comparison requires an LLM and was NOT run."), indent=2), encoding="utf-8")
