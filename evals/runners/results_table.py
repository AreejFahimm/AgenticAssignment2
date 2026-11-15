"""Build the results tables for README / report from evals/results/*.json (B5). Every number comes from a results file.

    python -m evals.runners.results_table                 # print markdown
    python -m evals.runners.results_table --write-readme  # refresh the <!-- RESULTS --> block in README.md
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
R = ROOT / "evals" / "results"


def _load(name: str):
    p = R / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def f(x, nd=3):
    return "n/a" if x is None else (f"{x:.{nd}f}" if isinstance(x, float) else str(x))


def render() -> str:
    out = []
    rag, outc, lat, ver = _load("rag_retrieval.json"), _load("outcomes.json"), _load("latency_bench.json"), _load("verification.json")
    if rag:
        reply = {a["variant"]: a for a in (outc or {}).get("arms", [])}
        rows = {r["variant"]: r for r in rag["rows"] if r["slice"] == "ALL"}
        out += ["### Retrieval variants (dev set, silver labels)", "",
                "| Variant | Evidence Recall@5 | MRR | nDCG@10 | Unsupported claims / proposal | Judge score | GigSim reply rate | p95 retrieval latency (s) | Cost / proposal (USD) |",
                "|---|---|---|---|---|---|---|---|---|"]
        unsup = f((ver or {}).get("unsupported_rate_after"))
        for v in ("v0", "v1", "v2", "v3", "v4", "v6", "v8", "best", "best_ctx", "ship"):
            if v in rows:
                r = rows[v]
                out.append(f"| {v} | {f(r['recall5'])} | {f(r['mrr'])} | {f(r['ndcg10'])} | {unsup} | see judge_calibration | "
                           f"{f(reply.get(v, {}).get('reply_rate'))} | {f(rag['latency_s'].get(v, {}).get('p95'), 2)} | 0 (offline profile) |")
        out.append("")
        if rag.get("v8_refusal_on_empty_gold", {}).get("total"):
            d = rag["v8_refusal_on_empty_gold"]
            out.append(f"V8 refused on {d['correct']}/{d['total']} jobs with no gold evidence.")
            out.append("")
    ab = _load("ablation.json")
    if ab:
        out += ["### Ablation of the best pipeline (one component at a time)", "", "| Arm | n | Recall@5 | MRR | nDCG@10 |", "|---|---|---|---|---|"]
        out += [f"| {r['arm']} | {r['n']} | {f(r['recall5'])} | {f(r['mrr'])} | {f(r['ndcg10'])} |" for r in ab["rows"] if r["slice"] == "ALL"]
        out.append("")
    dec = _load("decisions.json")
    if dec:
        o, s = dec["overall"], dec["scam"]
        out += ["### Decisions (bid vs skip, scam detection)", "",
                f"- bid-or-skip: precision {f(o['precision'])}, recall {f(o['recall'])}, F1 {f(o['f1'])}",
                f"- scam detection: precision {f(s['precision'])}, recall {f(s['recall'])}",
                f"- price inside market band: {f(dec['price_in_market_band']['rate'])} (n={dec['price_in_market_band']['n']})",
                f"- latency per job analysed p50/p95: {f(dec['latency_s']['analysed_p50'])}s / {f(dec['latency_s']['analysed_p95'])}s; per proposal p50/p95: {f(dec['latency_s']['proposal_p50'])}s / {f(dec['latency_s']['proposal_p95'])}s", ""]
    if dec:
        import yaml
        b = yaml.safe_load((ROOT / "agent" / "config.yaml").read_text(encoding="utf-8"))["budgets"]
        L = dec["latency_s"]
        out += ["### Budgets: declared vs measured (offline profile, CPU laptop, dev set)", "", "| Budget | Declared | Measured |", "|---|---|---|",
                f"| p95 latency per job analysed (s) | {b['p95_latency_s_per_job_analysed']} | {f(L['analysed_p95'])} |",
                f"| p95 latency per proposal (s) | {b['p95_latency_s_per_proposal']} | {f(L['proposal_p95'])} |",
                f"| USD per job analysed / per proposal | {b['usd_per_job_analysed']} / {b['usd_per_proposal']} | 0 / 0 (no paid API; LLM profiles not measured) |", ""]
    inj = _load("injection.json")
    if inj:
        out += ["### Prompt-injection attack success rate", "",
                f"- payload reaches the text that would be sent: defences OFF {f(inj['defences_off']['attack_success_rate'])}, ON {f(inj['defences_on']['attack_success_rate'])}; "
                f"injection FLAGGED by Risk Assessor: OFF {f(inj['defences_off']['flagged_rate'])}, ON {f(inj['defences_on']['flagged_rate'])}; auto-submitted jobs: {inj['defences_on']['auto_submitted']}"]
        pp = inj.get("paraphrase_probe")
        if pp:
            out.append(f"- attack that beats the regex layer: paraphrased instructions detected {pp['detected']}/{pp['n']} (detection rate {f(pp['detection_rate'])})")
        out.append("")
    if ver:
        out += ["### Claim verification", "",
                f"- planted fabrications removed: {ver['fabricated_removed']}/{ver['fabricated_planted']} (recall {f(ver['fabrication_recall'])}); "
                f"true claims wrongly removed: {ver['true_claims_wrongly_removed']}/{ver['true_claims_checked']}",
                f"- unsupported-claim rate before verification {f(ver['unsupported_rate_before'])} -> after {f(ver['unsupported_rate_after'])}", ""]
    if outc:
        out += ["### GigSim outcomes (simulated approval, fixed job set)", "", "| Arm | submitted | reply rate | interview rate | hire rate | Connects |", "|---|---|---|---|---|---|"]
        out += [f"| {a['variant']} | {a['submitted']} | {f(a['reply_rate'])} | {f(a['interview_rate'])} | {f(a['hire_rate'])} | {a['connects_spent']} |" for a in outc["arms"]]
        out.append("")
    abx = _load("ab_experiment.json")
    if abx:
        out += ["### X2 proposal A/B experiment", "",
                f"- n={abx['n_pairs']} paired jobs; reply rate A (evidence-first) {f(abx['reply_rate_A_evidence_first'])} vs B (concise+question) {f(abx['reply_rate_B_concise_question'])}; "
                f"diff {f(abx['diff_A_minus_B'])} (95% CI {abx['bootstrap_95ci']}); McNemar exact p={f(abx['mcnemar_exact_p'], 5)}; significant at 0.05: {abx['significant_at_0_05']}", ""]
    if lat:
        out += ["### Retrieval latency by design (E5 optimisation: reranker pool size)", "", "| Design | mean s/job | p95 s |", "|---|---|---|"]
        out += [f"| {k} | {f(v['mean_s'])} | {f(v['p95_s'])} |" for k, v in lat.items()]
        out.append("")
    cal = _load("judge_calibration.json")
    out += ["### Judge calibration", "",
            (f"weighted kappa {f(cal['weighted_kappa'])} on n={cal['n']} (your own labels)" if cal else "NOT YET CALIBRATED: label evals/datasets/judge_labels.csv, then run `python -m evals.runners.judge_calibration compute`. No judge score is reported until then."), ""]
    return "\n".join(out)


if __name__ == "__main__":
    md = render()
    if "--write-readme" in sys.argv:
        p = ROOT / "README.md"
        t = p.read_text(encoding="utf-8")
        new = f"<!-- RESULTS:BEGIN -->\n{md}\n<!-- RESULTS:END -->"
        t = re.sub(r"<!-- RESULTS:BEGIN -->.*?<!-- RESULTS:END -->", lambda _m: new, t, flags=re.S)
        p.write_text(t, encoding="utf-8")
        print("README results block updated")
    else:
        print(md)
