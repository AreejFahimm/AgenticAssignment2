.PHONY: install dev test eval seed demo lint web e2e openapi contract smoke-eval data
PY ?= python

install:
	$(PY) -m pip install -e ".[dev]"
	cd apps/web && npm install

# Build the datasets (needs Kaggle CSVs in data/raw/, see docs/DATA_CARD.md). Add --synthetic-fallback for an offline run.
data:
	cd scripts && $(PY) preprocess_jobs.py && $(PY) build_price_stats.py && $(PY) gen_personas.py && $(PY) build_dev_set.py

seed: data

# API (serves the built web app too) on :8000. GigSim-local runs in-process.
dev:
	GIGSIM_INPROCESS=1 REVIEWER_PASSWORD=$${REVIEWER_PASSWORD:-reviewer-pass-123} $(PY) -m uvicorn apps.api.main:app --reload --port 8000

web:
	cd apps/web && npm run build

openapi:
	$(PY) scripts/export_openapi.py && cd apps/web && npm run gen:api

test:
	$(PY) -m pytest -q

contract:
	$(PY) -m pytest tests/contract -q

e2e: web
	cd apps/web && npx playwright test

lint:
	ruff check .

# Full evaluation: writes evals/results/*.json (retrieval, ablation, decisions, injection, verification, outcomes, latency)
eval:
	$(PY) -m evals.runners.rag_eval --per-persona 60
	$(PY) -m evals.runners.ablation --per-persona 60
	$(PY) -m evals.runners.decision_eval --per-persona 60
	$(PY) -m evals.runners.verify_eval --per-persona 30
	$(PY) -m evals.runners.gigsim_outcomes --per-persona 25
	$(PY) -m evals.runners.ab_experiment --per-persona 25
	$(PY) -m evals.runners.latency_bench
	$(PY) -m evals.runners.results_table

# 30-job smoke eval used by CI (fails on regression, see evals/thresholds.yaml)
smoke-eval:
	$(PY) -m evals.runners.smoke_eval

demo:
	$(PY) scripts/run_job.py --persona fullstack_web_dev --index 3
