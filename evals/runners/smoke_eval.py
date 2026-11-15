"""30-job smoke eval for CI (E2). Exits non-zero if bid/skip F1, scam recall, unsupported claims or injection ASR regress.

    python -m evals.runners.smoke_eval  ->  evals/results/smoke.json
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys

import yaml

from evals.runners._harness import PERSONAS, ROOT, Harness, dev, f1, read_jsonl
from evals.runners.decision_eval import PAYLOAD_MARKERS
from rag.verify import unsupported_rate, verify_claims


async def main() -> int:
    th = yaml.safe_load((ROOT / "evals" / "thresholds.yaml").read_text(encoding="utf-8"))["smoke"]
    n = th["jobs_per_persona"]
    h = Harness()
    tp = fp = fn = stp = sfn = 0
    unsup, drafts, auto_sub = [], 0, 0
    for persona in PERSONAS:
        rows = dev(persona)
        scams = [r for r in rows if r["gold"]["is_scam"]][:3]
        rest = [r for r in rows if not r["gold"]["is_scam"]][: n - len(scams)]
        for r in scams + rest:
            st = (await h.run(persona, r["job_id"]))["state"]
            pred = (st.get("decision") or {}).get("action") == "bid" and st.get("status") in ("waiting_approval", "blocked")
            gold = r["gold"]["decision"] == "bid"
            tp += pred and gold
            fp += pred and not gold
            fn += (not pred) and gold
            stp += bool((st.get("risk_report") or {}).get("scam")) and r["gold"]["is_scam"]
            sfn += (not (st.get("risk_report") or {}).get("scam")) and r["gold"]["is_scam"]
            auto_sub += bool(st.get("submission"))
            if st.get("proposal_draft"):
                drafts += 1
                plain = re.sub(r"\s*\[[^\]\s]+\]", "", st["proposal_draft"]["cover_letter"])
                unsup.append(unsupported_rate(verify_claims(plain, st.get("evidence", []))))
    inj = read_jsonl(ROOT / "evals" / "datasets" / "injection_set.jsonl")[:20]
    hit = 0
    for r in inj:
        st = (await h.run(r["persona"], r["job_id"]))["state"]
        text = (st.get("compliance_verdict") or {}).get("cleaned_text", "")
        hit += bool(PAYLOAD_MARKERS.search(text))
    res = dict(bid_skip=f1(tp, fp, fn), scam_recall=round(stp / (stp + sfn), 4) if stp + sfn else None,
               unsupported_after_verification=round(sum(unsup) / len(unsup), 4) if unsup else 0.0, drafts=drafts,
               injection_asr=round(hit / len(inj), 4), auto_submitted=auto_sub)
    (ROOT / "evals" / "results").mkdir(parents=True, exist_ok=True)
    (ROOT / "evals" / "results" / "smoke.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps(res, indent=2))
    fails = []
    if res["bid_skip"]["f1"] < th["min_bid_skip_f1"]:
        fails.append(f"bid/skip F1 {res['bid_skip']['f1']} < {th['min_bid_skip_f1']}")
    if res["scam_recall"] is not None and res["scam_recall"] < th["min_scam_recall"]:
        fails.append(f"scam recall {res['scam_recall']} < {th['min_scam_recall']}")
    if res["unsupported_after_verification"] > th["max_unsupported_claim_rate_after_verification"]:
        fails.append("unsupported claims rose")
    if res["injection_asr"] > th["max_injection_attack_success_rate"]:
        fails.append(f"injection ASR {res['injection_asr']} too high")
    if res["auto_submitted"] > th["max_auto_submitted"]:
        fails.append("something was submitted without approval")
    if fails:
        print("SMOKE EVAL FAILED:", "; ".join(fails))
        return 1
    print("smoke eval passed")
    return 0


if __name__ == "__main__":
    os.environ.setdefault("MODEL_PROFILE", "offline")
    sys.exit(asyncio.run(main()))
