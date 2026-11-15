# 3-minute demo video script (portfolio deliverable)

Required content: **one job from inbox to approved proposal, one scam caught, one injected instruction ignored, one client reply handled.**

| Time | Show | Say |
|---|---|---|
| 0:00 | Sign in as the reviewer, Inbox | "GigBid scouts jobs, scores fit and risk, and only a human sends anything." |
| 0:20 | Click *Scan*, then *Run* on a job (live node-by-node timeline) | "Analyst, Risk and Fit run in parallel." |
| 0:45 | Job detail: requirement→evidence matrix, price rationale | "Every requirement maps to portfolio evidence; price comes from market bands." |
| 1:05 | Proposal studio: hover a sentence → evidence popover; dry-run preview; click Approve | "Every claim links to evidence; nothing is sent until I approve." |
| 1:35 | Inbox filter *skip*: open the **scam** job (off-platform contact / free work) | "Risk Assessor caught it; no draft was written." |
| 1:55 | Open an **injection** job (see `evals/datasets/injection_set.jsonl`), show the flag and that the draft has no attacker text | "The job post tried to give the AI orders; it was delimited, flagged and neutralised, and nothing is auto-sent." |
| 2:20 | Messages: client reply → suggested reply with interview slots → Approve | "Client Liaison drafts; I approve before it sends." |
| 2:45 | Pipeline board + Analytics; mention memory viewer in Settings | "Outcomes feed back into what GigBid learns, and I can delete anything it learned." |

Recording: `cd apps/web && npx playwright test demo.spec.ts` records the happy path (video in `test-results/`); record the scam and injection parts by hand
(use the injection job ids from `evals/datasets/injection_set.jsonl`; analyse them via `POST /jobs/{job_id}/analyse`).
