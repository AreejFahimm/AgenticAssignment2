#!/usr/bin/env bash
# Sequential full evaluation (each step writes evals/results/*.json). Logs to evals/logs/.
set -u
cd "$(dirname "$0")/.."
PY=.venv/Scripts/python.exe
[ -x "$PY" ] || PY=python
mkdir -p evals/logs
run() { name=$1; shift; echo "== $name $(date +%T)"; "$PY" -u "$@" > "evals/logs/$name.log" 2>&1 || echo "FAILED: $name"; }
run rag_eval2   -m evals.runners.rag_eval --per-persona 60 --variants v6 v8 best_ctx --merge
run latency     -m evals.runners.latency_bench
run decisions   -m evals.runners.decision_eval --per-persona 60
run verify      -m evals.runners.verify_eval --per-persona 30
run outcomes    -m evals.runners.gigsim_outcomes --per-persona 25
run ab          -m evals.runners.ab_experiment --per-persona 25
run tools       -m evals.runners.tool_granularity
run compare     -m evals.runners.agent_comparison --per-persona 15
run ablation    -m evals.runners.ablation --per-persona 40
echo "ALL DONE $(date +%T)"
