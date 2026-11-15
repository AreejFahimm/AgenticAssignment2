#!/usr/bin/env bash
# Re-run everything that depends on the SHIPPED retrieval variant (config rag.variant).
set -u
cd "$(dirname "$0")/.."
PY=.venv/Scripts/python.exe
run() { name=$1; shift; echo "== $name $(date +%T)"; "$PY" -u "$@" > "evals/logs/$name.log" 2>&1 || echo "FAILED: $name"; }
run rag_ship   -m evals.runners.rag_eval --per-persona 60 --variants ship --merge
run decisions  -m evals.runners.decision_eval --per-persona 60
run verify     -m evals.runners.verify_eval --per-persona 30
run outcomes   -m evals.runners.gigsim_outcomes --per-persona 25
run ab         -m evals.runners.ab_experiment --per-persona 25
run compare    -m evals.runners.agent_comparison --per-persona 15
run smoke      -m evals.runners.smoke_eval
echo "FINAL DONE $(date +%T)"
