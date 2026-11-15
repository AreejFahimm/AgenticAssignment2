"""CI guard: every measured number in README.md must come from evals/results/ (R: numbers trace to files).

Convention: measured numbers live ONLY inside the auto-generated block
    <!-- RESULTS:BEGIN --> ... <!-- RESULTS:END -->
produced by `python -m evals.runners.results_table`. This script regenerates the block text from evals/results/*.json and
fails if the README block differs (stale or hand-edited numbers). Outside the block, README must not quote decimals that
look like metrics (e.g. 0.412) unless the same literal appears in a results file.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
readme = (ROOT / "README.md").read_text(encoding="utf-8") if (ROOT / "README.md").exists() else ""
m = re.search(r"<!-- RESULTS:BEGIN -->(.*?)<!-- RESULTS:END -->", readme, re.S)
if not m:
    sys.exit("README.md has no <!-- RESULTS:BEGIN --> block; run python -m evals.runners.results_table")

sys.path.insert(0, str(ROOT))
from evals.runners.results_table import render  # noqa: E402

expected = render().strip()
if m.group(1).strip() != expected:
    sys.exit("README results block is stale or hand-edited. Regenerate: python -m evals.runners.results_table --write-readme")

outside = readme.replace(m.group(0), "")
blob = " ".join(p.read_text(encoding="utf-8") for p in (ROOT / "evals" / "results").glob("*.json"))
bad = [n for n in set(re.findall(r"(?<![\w.])0\.\d{2,}(?![\w.])", outside)) if n not in blob and n not in ("0.60", "0.70", "0.45", "0.30")]
if bad:
    sys.exit(f"README quotes numbers not found in evals/results: {bad}")
print("README numbers trace to evals/results")
