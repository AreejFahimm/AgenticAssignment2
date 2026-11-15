#!/usr/bin/env bash
cd "$(dirname "$0")/.."
PY=.venv/Scripts/python.exe
for s in "outcomes -m evals.runners.gigsim_outcomes --per-persona 25" "ab -m evals.runners.ab_experiment --per-persona 25" "smoke -m evals.runners.smoke_eval"; do
  set -- $s; n=$1; shift; echo "== $n $(date +%T)"; "$PY" -u "$@" > "evals/logs/$n.log" 2>&1 || echo "FAILED: $n"
done
echo "FINAL2 DONE"
