# Runbook

## Run locally
```bash
python -m venv .venv && .venv/Scripts/activate        # or source .venv/bin/activate
pip install -e ".[dev]" && cd apps/web && npm install && npm run build && cd ../..
cp .env.example .env                                   # fill REVIEWER_PASSWORD, APP_SECRET_KEY
make data                                              # needs Kaggle CSVs in data/raw/, or: python scripts/preprocess_jobs.py --synthetic-fallback ...
make dev                                               # http://localhost:8000 (API + built web app, GigSim-local in-process)
```
Everything also runs with `docker compose -f infra/docker-compose.yml up --build` (**not validated here: Docker was unavailable on the dev machine**).

## Profiles
`MODEL_PROFILE=offline` (default): deterministic heuristics for analyst/risk/writer/critic/liaison (CI and demos, no GPU, no key).
`MODEL_PROFILE=open`: set `LLM_BASE_URL` (Ollama `http://localhost:11434/v1`, vLLM, llama.cpp server, Groq, OpenRouter, Together) and `LLM_API_KEY`; per-node models in `agent/config.yaml`.
`MODEL_PROFILE=paid`: optional, `PAID_LLM_BASE_URL`. **The LLM profiles are wired and prompts exist, but the measured results in `evals/results/` were produced on the offline profile.**

## Scheduling and live-mode politeness (E1)
- Scouting and long runs execute in `worker/scheduler.py` (asyncio) or `worker/arq_settings.py` (Redis/Arq; untested here), never in a request.
- Saved searches: interval floor **60 minutes** enforced in the API schema and the scheduler; default **240 minutes**. At most 8 jobs queued per scan, 2 concurrent runs.
- Live Upwork mode: read tools only on that schedule; no scraping, no browser automation, no cookies; proposals and messages are created as drafts only after in-app approval
  and are confirmed by the user on Upwork. Rationale for 240 minutes: job feeds change slowly relative to a freelancer's reaction time, and it keeps well below anything that resembles polling.
- Idempotency: thread id `<user>.<job_id>`; Scout's `SeenStore`; submit keys derive from the thread id.

## Degraded mode (viva item 1)
Stop the marketplace (or make the GigSim URL unreachable). `MCPHub` retries with backoff, raises `MarketplaceDown`; the runner sets `marketplace_ok=false`, queues the scan,
marks runs `degraded`; the UI shows the red banner "Marketplace unavailable … queued"; when it is back, `health_loop` (15 s) or "Retry now" re-drives the queued work.
Code: `agent/mcp_client.py` (raise), `apps/api/runner.py` (`_mark_down`, `redrive_degraded`), `apps/web/src/components/StatusBanner.tsx` (banner).

## Exactly-once demo (viva item 2)
1. Run a job to approval (UI) → stop the API process → start it again → the approval is still in the list (`/approvals`).
2. Approve once → submitted. Approve again → HTTP 409. Connects balance dropped by exactly one proposal's cost.
Automated: `pytest tests/integration/test_bid_graph.py -k restart`.

## Budgets (E5)
Declared in `agent/config.yaml` under `budgets`; measured values are in `evals/results/decisions.json` and `latency_bench.json`. Optimisation that helped: halving the reranker candidate
pool (see `latency_bench.json` and the ablation row "rerank pool 10").

## Secrets
Only from env (`.env.example` lists every variable). OAuth tokens are Fernet-encrypted (`TOKEN_ENC_KEY`), never logged; logs and traces are PII-masked; every query is scoped by user id.

## Backups / reset
`data/processed/*.sqlite` hold checkpoints, app DB and memory; delete to reset. Raw Kaggle data and the hidden test set are never committed.
