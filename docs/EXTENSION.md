# Signature extension: X2 Proposal experiments

**What it is.** The Writer has two strategies selectable per thread (`state["strategy"]`):
- **A `evidence_first`**: up to three cited past-work sentences, honest gaps, a milestone offer.
- **B `concise_question`**: one cited sentence plus a clarifying question to the client.

`evals/runners/ab_experiment.py` runs both on the **same** fixed job set (paired design, separate marketplace users) in GigSim and reports reply-rate for each,
the difference with a bootstrap 95% CI, an exact McNemar test on the discordant pairs and a two-proportion z-test. Output: `evals/results/ab_experiment.json`
(rendered in the README results block).

**How it was measured and what it does NOT show.** GigSim-local clients are rule-based (skill mentions, genericness, price), so the experiment validates the machinery
(assignment, pairing, statistics, reporting) and tells you what the simulator rewards; it is not evidence about real clients. Replies are deterministic per proposal id,
so a significant difference comes from the letter, not from luck. A real deployment would assign strategies randomly per job and run McNemar on matched categories.

**Reproduce:** `python -m evals.runners.ab_experiment --per-persona 25`.
