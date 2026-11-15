# Change request (platform policy update, released 2 Nov 2026) — how GigBid absorbs it

**Status: the policy text was not available to the assistant that built this repo; fill in the first section yourself from the Classroom announcement.**

## 1. What changed (YOU fill this in)
- Rule/cost introduced: _…_
- Effective for: _…_

## 2. Where to make the change (designed to be config-only)
| If the update is… | Edit | Code change needed? |
|---|---|---|
| a new Connects cost or surcharge (e.g. premium jobs cost more) | GigSim policy `gigsim_local/platform_policy.json` (`connects_cost_per_proposal`, `premium_job_extra_connects`, `premium_budget_threshold`); `pricing.max_connects_per_bid` in `agent/config.yaml` | No: `connects_cost` comes from the marketplace and Pricing reads the cap from config |
| a minimum/maximum cover-letter length | `min_cover_letter_chars` in `platform_policy.json` (fetched live by the runner and enforced by Compliance) and `compliance.*` in config | No |
| a daily proposal cap | `max_proposals_per_day` in `platform_policy.json` | No (the marketplace returns 429; the adapter treats it as unavailable and the run is queued) |
| newly banned phrases / behaviours | `compliance.banned_phrases` in config (+ `data/policy_pack/`) | No |
| a different ROI rule for whether a job is worth the Connects | `pricing.min_expected_value_ratio`, `pricing.max_connects_per_bid` | No |
| a new rule that needs a new check | new function in `agent/nodes/compliance.py` or `pricing.py` | Yes (small) |

## 3. Measure it (report section 6)
Record: start time, finish time, files changed and lines changed (`git diff --stat`), tests added. Viva item 10 asks "how many lines changed to absorb the change request? Show the diff."
```bash
git diff --stat <commit-before>..<commit-after>
```
Suggested proof: a test in `tests/integration/test_change_request.py` that sets the new policy value, runs a job and asserts the new behaviour (skip / watch / blocked / queued).
