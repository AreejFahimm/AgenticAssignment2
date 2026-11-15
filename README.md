# GigBid: a multi-agent freelancer copilot

> A team of LangGraph agents finds freelance jobs, judges whether they are worth bidding on, writes proposals where **every claim links to portfolio evidence**,
> and manages client conversations. **A human approves every proposal and message** before anything leaves the system.

**Live demo:** _TODO: public URL (reviewer login is in the Classroom private comment)_ · **Demo GIF / 3-min video:** _TODO (record with `apps/web/tests/e2e/demo.spec.ts`, see docs/DEMO_SCRIPT.md)_ ·
**Traces:** open any run in the app (Runs → Open trace), or see `docs/traces/` _TODO: add three public trace links_

## What it does
1. Sign in, connect a marketplace (GigSim simulator today; the official Upwork MCP server in live mode), upload a portfolio, set rates, filters and a weekly Connects budget.
2. A worker scouts saved searches on a conservative schedule; each job runs through a graph: **Job Analyst ‖ Risk Assessor ‖ Fit Matcher** (parallel) → decision → pricing.
3. For a recommended job it drafts a proposal; a **claim verifier** strips anything the portfolio does not support, a **Critic** (≤ 2 loops) and a **Compliance Guard** check it.
4. The graph **pauses at an `interrupt()`**. You review the draft with evidence on hover, a dry-run of what will be sent and its Connects cost, then approve, edit or reject.
5. Replies from clients are classified, answered (with interview slots) and again require your approval.

## Architecture
See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and the Mermaid graphs generated from code ([bid graph](docs/images/bid_graph.mmd), [conversation graph](docs/images/conversation_graph.mmd)).
Tools: [docs/TOOLS.md](docs/TOOLS.md). Decisions: [docs/adr/](docs/adr). Data: [docs/DATA_CARD.md](docs/DATA_CARD.md). Operations: [docs/RUNBOOK.md](docs/RUNBOOK.md). Extension (X2): [docs/EXTENSION.md](docs/EXTENSION.md).

## Results
Every number below is generated from `evals/results/*.json` by `python -m evals.runners.results_table --write-readme`; CI fails if this block is stale.
All results are from the **offline profile** (deterministic heuristics, no LLM) on **silver-labelled** dev data (real Kaggle job posts + synthetic personas/clients). Read the limits in
[docs/DATA_CARD.md](docs/DATA_CARD.md) and the report before trusting any number.

<!-- RESULTS:BEGIN -->
### Retrieval variants (dev set, silver labels)

| Variant | Evidence Recall@5 | MRR | nDCG@10 | Unsupported claims / proposal | Judge score | GigSim reply rate | p95 retrieval latency (s) | Cost / proposal (USD) |
|---|---|---|---|---|---|---|---|---|
| v0 | 0.350 | 0.540 | 0.415 | 0.000 | see judge_calibration | 0.278 | 0.52 | 0 (offline profile) |
| v1 | 0.321 | 0.500 | 0.387 | 0.000 | see judge_calibration | n/a | 0.14 | 0 (offline profile) |
| v2 | 0.273 | 0.412 | 0.343 | 0.000 | see judge_calibration | 0.355 | 0.03 | 0 (offline profile) |
| v3 | 0.344 | 0.453 | 0.382 | 0.000 | see judge_calibration | n/a | 5.19 | 0 (offline profile) |
| v4 | 0.261 | 0.354 | 0.306 | 0.000 | see judge_calibration | n/a | 0.03 | 0 (offline profile) |
| v6 | 0.350 | 0.455 | 0.387 | 0.000 | see judge_calibration | n/a | 3.89 | 0 (offline profile) |
| v8 | 0.212 | 0.337 | 0.226 | 0.000 | see judge_calibration | n/a | 6.47 | 0 (offline profile) |
| best | 0.369 | 0.501 | 0.415 | 0.000 | see judge_calibration | 0.457 | 4.73 | 0 (offline profile) |
| best_ctx | 0.386 | 0.522 | 0.457 | 0.000 | see judge_calibration | n/a | 3.48 | 0 (offline profile) |
| ship | 0.505 | 0.643 | 0.579 | 0.000 | see judge_calibration | 0.375 | 0.20 | 0 (offline profile) |

V8 refused on 7/11 jobs with no gold evidence.

### Ablation of the best pipeline (one component at a time)

| Arm | n | Recall@5 | MRR | nDCG@10 |
|---|---|---|---|---|
| V0 baseline | 112 | 0.357 | 0.527 | 0.413 |
| best (decompose+hybrid+rerank) | 112 | 0.359 | 0.485 | 0.408 |
| best + contextual indexing (V6) | 112 | 0.377 | 0.502 | 0.447 |
| best + outcome boost | 112 | 0.356 | 0.473 | 0.397 |
| best - decompose | 112 | 0.331 | 0.438 | 0.378 |
| best - hybrid | 112 | 0.346 | 0.486 | 0.393 |
| best - rerank | 112 | 0.414 | 0.600 | 0.465 |
| best, rerank pool 10 (latency opt.) | 112 | 0.383 | 0.516 | 0.454 |
| contextual dense only (V6 dense) | 112 | 0.372 | 0.497 | 0.424 |
| decompose+hybrid+contextual, no rerank | 112 | 0.511 | 0.633 | 0.575 |
| decompose+hybrid, no rerank | 112 | 0.414 | 0.600 | 0.465 |
| hybrid+contextual, no rerank | 112 | 0.287 | 0.404 | 0.365 |

### Decisions (bid vs skip, scam detection)

- bid-or-skip: precision 0.750, recall 0.536, F1 0.625
- scam detection: precision 0.905, recall 1.000
- price inside market band: 0.800 (n=60)
- latency per job analysed p50/p95: 0.403s / 0.647s; per proposal p50/p95: 0.504s / 0.696s

### Budgets: declared vs measured (offline profile, CPU laptop, dev set)

| Budget | Declared | Measured |
|---|---|---|
| p95 latency per job analysed (s) | 15 | 0.647 |
| p95 latency per proposal (s) | 30 | 0.696 |
| USD per job analysed / per proposal | 0.01 / 0.05 | 0 / 0 (no paid API; LLM profiles not measured) |

### Prompt-injection attack success rate

- payload reaches the text that would be sent: defences OFF 0.000, ON 0.000; injection FLAGGED by Risk Assessor: OFF 0.000, ON 1.000; auto-submitted jobs: 0
- attack that beats the regex layer: paraphrased instructions detected 2/10 (detection rate 0.200)

### Claim verification

- planted fabrications removed: 100/100 (recall 1.000); true claims wrongly removed: 0/101
- unsupported-claim rate before verification 0.600 -> after 0.000

### GigSim outcomes (simulated approval, fixed job set)

| Arm | submitted | reply rate | interview rate | hire rate | Connects |
|---|---|---|---|---|---|
| generic | 75 | 0.013 | 0.000 | 0.000 | 600 |
| v0 | 36 | 0.278 | 0.167 | 0.056 | 288 |
| v2 | 31 | 0.355 | 0.097 | 0.000 | 248 |
| best | 35 | 0.457 | 0.057 | 0.029 | 280 |
| ship | 40 | 0.375 | 0.125 | 0.025 | 320 |

### X2 proposal A/B experiment

- n=40 paired jobs; reply rate A (evidence-first) 0.400 vs B (concise+question) 0.425; diff -0.025 (95% CI [-0.25, 0.2]); McNemar exact p=1.00000; significant at 0.05: False

### Retrieval latency by design (E5 optimisation: reranker pool size)

| Design | mean s/job | p95 s |
|---|---|---|
| v0 | 0.114 | 0.446 |
| v2 hybrid | 0.008 | 0.022 |
| v3 rerank pool=20 | 1.508 | 4.065 |
| v3 rerank pool=10 | 0.685 | 1.629 |
| best pool=20 | 1.485 | 3.714 |
| best pool=10 | 0.700 | 1.774 |

### Judge calibration

NOT YET CALIBRATED: label evals/datasets/judge_labels.csv, then run `python -m evals.runners.judge_calibration compute`. No judge score is reported until then.

<!-- RESULTS:END -->

## Quick start
```bash
pip install -e ".[dev]" && (cd apps/web && npm install && npm run build)
python scripts/preprocess_jobs.py --synthetic-fallback   # or put the Kaggle CSVs in data/raw/ (docs/DATA_CARD.md)
make data && make dev                                      # http://localhost:8000
make test && make e2e                                      # pytest (unit, contract, integration) + Playwright
make eval                                                  # writes evals/results/*.json
```
`docker compose -f infra/docker-compose.yml up --build` starts API+web, worker, GigSim, three MCP servers, Postgres, Redis (and Ollama with `--profile llm`); it was not validated on the dev machine.

## Pinned versions
Python 3.12.9 · langgraph 1.2.20 · mcp 1.30.0 · langchain-mcp-adapters 0.3.2 · fastapi 0.162.4 · fastembed 0.9.1 (BAAI/bge-small-en-v1.5, Xenova/ms-marco-MiniLM-L-6-v2) · React 18.3 / Vite 5.4 / Playwright 1.49 (full list in `pyproject.toml`, `apps/web/package.json`).

## Honest status
Done and tested: MCP servers (3) with schemas/annotations/idempotency/dry-run/auth/audit, marketplace port + GigSim adapter, both graphs with parallel branches, bounded critic loop,
interrupt approvals that survive restarts, style/outcome memory with promotion rules, advanced RAG variants + claim verification + evals, FastAPI + SSE, React UI (all screens), 7 Playwright tests, worker scheduler.
Not done / not run: live Upwork adapter (needs credentials), GitHub MCP ingestion against real repos, LLM-profile measurements, judge calibration (needs **your** 30 labels), the ReAct-vs-supervisor comparison,
Docker compose validation, public deployment, demo video, write-up, Postgres checkpointer test, a real vector database. See the report.

## Safety rules enforced in code
Untrusted job posts and client messages are delimited, scanned and neutralised; nothing is sent without an approval interrupt; unsupported claims are removed; contact details/guarantees/off-platform asks are stripped;
PII is masked in logs, traces and the audit log; OAuth tokens are encrypted; every query is tenant-scoped; no scraping, no browser automation, no cookies.
