# GigBid: engineering design review (AI-4016 R&D report)

**Author:** _your name / roll number_ · **Repo:** _link_ · **Live:** _link_ · **Everything below cites `evals/results/*.json` (tables in Appendix A are generated from them) or a file in the repo.**
**Read first (scope):** all measurements use the **offline profile** (deterministic heuristics for analyst/risk/writer/critic, no LLM) on **silver labels** (rule-derived, not human-checked) over **real Kaggle job posts + synthetic personas/clients**. LLM-profile quality, live Upwork, Docker and Postgres were not run.

## 1. Problem and constraints
A freelancer loses hours scanning feeds, burns paid Connects on unwinnable jobs, sends generic proposals and meets scams (free work, off-platform payment, prompt-injection text). GigBid automates discovery, assessment and drafting; **the human decides**.
Never automated: sending a proposal or message, spending Connects, accepting terms, contacting a client off-platform, claiming experience the portfolio does not show. Enforced by a LangGraph `interrupt()` that is the only path to the `submit`/`send` nodes (ADR 0002); there is no auto-send setting.
Declared budgets (`agent/config.yaml`): p95 latency 15 s per job analysed and 30 s per proposal; USD 0.01 / 0.05 per job / proposal. Measured: Appendix A "Budgets" (0.65 s / 0.70 s p95 offline on a CPU laptop; USD 0 because no paid API was called, so these say nothing about LLM cost).

## 2. Architecture
Two durable hand-written LangGraph graphs (diagrams: `docs/images/*.mmd`, rationale per agent: `docs/ARCHITECTURE.md`).
**Bid graph** (thread per job): Scout (dedup) → **Analyst ‖ Risk ‖ Fit** via `Send` → decide → Pricing → Writer → claim verifier → Critic (≤ 2 send-backs) → Compliance → dry-run preview → **approval interrupt** → submit (exactly-once keys).
**Conversation graph** (thread per client conversation): Liaison (intent, reply, slots) → approval → send (+ tentative hold).
**One marketplace port** (`agent/marketplace_port.py`) with a GigSim adapter (tested) and a live Upwork adapter skeleton (untested); agents only call **MCP tools** (Portfolio, Marketplace, Workspace servers; per-agent allowlists in `agent/mcp_client.py`). **State / trace / memory are kept apart** (ADR 0006): checkpointed state; JSON trace + audit log; long-term memory only through `promotion_rules.py` (style: ≥ 2 occurrences on ≥ 2 jobs; outcome: ≥ 3 samples per category).
Stores: SQLite checkpointer (Postgres supported, untested), app DB, LangGraph store, in-process NumPy+BM25 index (no vector database). Frontend: React/Vite/TS with a client generated from FastAPI's OpenAPI.

## 3. R&D question A: tool granularity
*Hypothesis (before running):* BEST (rewritten, task-oriented descriptions) ≥ FINE (27 one-purpose tools) > COARSE (3 mega-tools); COARSE uses the fewest tokens.
*Setup:* 40 tasks with known correct tool/arguments (`evals/runners/tool_granularity.py`); an **offline embedding selector** over tool names+descriptions (no LLM). *Results* (`tool_granularity.json`): BEST 0.80 selection accuracy (388 prompt-tokens of tool list), FINE 0.50 (232), COARSE 0.50 at server level only (52).
*Conclusion:* description quality, not tool count, drives separability; coarse tools are cheap but their action argument is invisible to selection. **Limits:** this measures description discriminability, not agent behaviour; argument accuracy needs an LLM run and was **not measured**.

## 4. R&D question B: RAG
*Variants implemented:* V0 naive dense; V1 requirement decomposition; V2 hybrid BM25+dense (RRF); V3 cross-encoder rerank; V4 outcome-aware boost; V6 contextual chunks; V8 corrective RAG as a LangGraph loop (threshold calibrated on dev, checked on held-out: `v8_calibration.json`, F1 0.52 on held-out vs 0.0 at the default). Not built: V5, V7, V9.
*Hypothesis (before running):* decomposition + hybrid + rerank raises Recall@5 over V0 by ≥ 10 points on jobs with ≥ 3 requirements. **Refuted:** `best` gained +1.9 points overall (0.369 vs 0.350) and lost MRR; hybrid alone (V2) and the outcome boost (V4) were *worse* than V0.
*Ablation* (Appendix A, n = 112 jobs with gold evidence): removing the reranker **improved** Recall@5 (0.359 → 0.414): the MiniLM cross-encoder is out-of-domain for this corpus and costs ~1.5 s/job. The winning arm is **decomposition + hybrid + contextual chunks, no rerank: Recall@5 0.511, MRR 0.633, nDCG@10 0.575 vs V0 0.357 / 0.527 / 0.413 (+15.4 points)**, at ~0.2 s p95 retrieval. **That is what ships** (`rag.variant: ship`). Caveat: contextual chunks expose the same skill metadata that defines the silver gold labels, so part of the gain is circular; the honest reading is "metadata-aware indexing helps when skills are implied rather than named", not "+15 points on real portfolios".
*By persona and job type:* `rag_retrieval.json` / `ablation.json` slices (multi- vs few-requirement jobs show similar V0 vs best gaps; decomposition helped less than hypothesised).
*Where better retrieval did not help replies:* in GigSim, V0, V2, `best` and `ship` reply rates are within noise of each other (Appendix A), because the simulated clients reward skill mentions and non-generic text, which every grounded variant provides; the large effect is grounded vs generic (control arm).
*Claim verification (B3):* the offline writer is extractive, so natural drafts contain no fabrications. We planted 90 fabricated experience sentences into real drafts: **all 90 removed; 0 of 104 true claims removed; unsupported-claim rate 0.51 → 0.00**. This is an easy test (fabrications contain numbers/entities absent from evidence); paraphrased or partially true fabrications are not tested.
*Judge calibration:* **not done: needs the author's 30 labels** (`judge_calibration prepare/compute`). No judge score is reported. Human pairwise panel: **not run** (`pairwise_panel`).

## 5. R&D question C: is multi-agent worth it?
**Not answered as specified.** The requested comparison (single ReAct agent vs `langgraph-supervisor` vs this graph) needs an LLM that chooses tools; none was run (`agent_comparison.py` contains the stubs). What was measured instead is an **ablation of the graph's safeguards** (`agent_comparison.json`, 57 jobs): removing the Risk Assessor lets 2 of 12 planted scams reach the approval screen (0 with it) and lowers bid/skip F1 0.552 → 0.516; removing verifier+Critic or Compliance changed nothing measurable offline, because the extractive writer never produces unsupported claims or contact details. So the evidence for multi-agent value here is the **parallel risk veto** and the **approval architecture**, not the Critic/Compliance loops, and a ReAct baseline might win on easy jobs: unknown.

## 6. The change request
**Fill in from the 2 Nov Classroom announcement.** Design for it: rules, thresholds and prompts are data (`agent/config.yaml`, `gigsim_local/platform_policy.json`, fetched live by the runner; ADR 0007; `docs/CHANGE_REQUEST.md` maps each kind of rule to the file to edit). Record: time taken, `git diff --stat`, and a test.

## 7. Signature extension (X2: proposal experiments)
Two writer strategies (evidence-first vs concise+question) A/B-tested on the same jobs in GigSim with paired design, exact McNemar and bootstrap CI (`docs/EXTENSION.md`, Appendix A). Result: **no significant difference** at this sample size. The simulator is rule-based, so this validates the experiment machinery, not client behaviour.

## 8. Failure analysis
Grouped from the dev runs and development incidents (fix tried → worked?):
| Class | Example | Fix | Worked |
|---|---|---|---|
| Wrong skip / missed evidence | bid recall only 0.54: many gold-"bid" real jobs get fit < 0.30 (keyword skills noisy, e.g. "Data Entry" tagged "excel") | none beyond contextual retrieval | partly |
| Tool/graph error | `except Exception` swallowed `GraphInterrupt` → every approval became dead_letter | re-raise `GraphBubbleUp` | yes |
| Unsupported claim (detector) | claim regex corrupted by a shell heredoc, verifier passed everything | fixed + printed labels on real drafts | yes |
| Compliance miss | email regex ate the sentence-final period, deleting valid sentences / blocking a valid edit | tighten regex | yes |
| Cross-tenant bug (simulator) | idempotency keys global, not per user | scope by (user, key) | yes |
| Generic opening / bad text | real posts end in boilerplate ("Budget: … Skills: …") polluting requirements and drafts | strip trailer in preprocessing | yes |
| Retrieval | V8 refused nothing at its default threshold | calibrate on dev, check on held-out | yes (F1 0.52) |
| Injection | paraphrased instructions evade the regex (detected 2/10) | none; approval gate limits damage | no |
| Mispriced | 20% of bids outside the market p25–p75 band | not fixed | – |
| Tool error / degraded | marketplace down | queue + banner + redrive (tested) | yes |
**Concrete failed dev jobs** (`evals/runners/failed_jobs.py` → `failed_jobs.json`; 120 dev jobs examined, 48 failures: **26 wrong skip, 11 wrong bid, 11 mispriced, 0 missed evidence**). Open any id in the app (Analyse → Run → trace):
| # | Class | Job id | Title | What happened | Cause / fix tried |
|---|---|---|---|---|---|
| 1 | wrong skip | job-2759dad0f4 | Mini-Leads AI chat driven CRM | fit 0.40 → "watch" (gold: bid) | fit threshold 0.45 vs noisy lexical strength; not fixed |
| 2 | wrong skip | job-1327e7c354 | Network Engineer - OPENAI API/ChatGPT Payment Problem | fit 0.39 → watch | keyword-extracted skills ("openai") overstate relevance in gold; label noise |
| 3 | wrong skip | job-0c90cb12c0 | Android Studio Developer needed for prototype App | fit 0.23 → skip (gold overlap 1.0) | gold skill tag is a false positive on a mobile job; label noise |
| 4 | wrong skip | job-726f549d7c | AI Developer | budget 25 below floor 30 → skip although fit 0.89 | floor rule (config `pricing.floor_hourly_multiplier`) is stricter than the gold rule |
| 5 | wrong bid | job-197c1802cc | AI Model/Tool Developer for Building Damage Assessment | bid at fit 0.56, 4/6 requirements evidenced (gold: skip, budget rule) | gold excludes on budget, graph accepts a wide band |
| 6 | wrong bid | job-3d96bed306 | AI Machine Learning Developer - LLM AI Lead Gen | bid, fit 0.75 | same as 5 |
| 7 | wrong bid | job-68ba2b3d24 | Write Unity gaming app relying on ChatGPT API | bid, fit 1.0 from a single requirement ("1/1") | one-requirement jobs saturate fit; needs a minimum-requirements rule |
| 8 | wrong bid | job-4d4ab39b12 | Create image and data repository | bid at fit 0.50 (3/6 evidenced) | threshold 0.45 admits half-matched jobs |
| 9 | mispriced | job-655d2fa215 | JavaScript Web Scraper | bid 25.5 vs band 10–24 | the persona's hourly floor (30 × 0.85) exceeds the market p75, so the floor overrides the band by design |
| 10 | mispriced | job-c4fc134f56 | Javascript - Adjustment in Wordpress Using Divi Theme | bid 25.5 vs band 11.11–25 | same |
| 11 | mispriced | job-3e89326a4d | Next.js & Babylon.js Expert For House Configurator | bid 25.5 vs band 11.11–25 | same |
| 12 | mispriced | job-9ae1585805 | Basic Meat & Potatoes SEO and Google Shopping Work on Shopify Store | bid 25.5 vs band 10–25 | same |
Take-away: most "failures" are label noise or a deliberate floor rule, not agent errors; the real defect is #7 (single-requirement saturation), not yet fixed.

## 9. Safety and platform respect
Enforced: untrusted text delimited/scanned/neutralised; nothing sent without an approval interrupt (auto-submitted jobs: 0 in every eval); unsupported claims removed; contact details/guarantees/off-platform asks stripped; PII masked in logs, traces and the audit log; OAuth tokens Fernet-encrypted; every query tenant-scoped; no scraping/browser automation/cookies.
Injection results (Appendix A): the Risk Assessor flags 100% of the planted injections with defences on (0% off); the payload never reached the text to be sent in either mode because the offline writer is extractive, so this does **not** show the defence preventing harm. **An attack that beats it:** paraphrased instructions (2/10 detected). With an LLM writer that risk is real; the approval gate is the backstop. Upwork: live mode not exercised.

## 10. Hidden test results against declared budgets
**Not available yet:** the instructor runs the hidden set after the deadline. Dev-set numbers vs budgets are in Appendix A. Do not read the dev results as hidden-set predictions (silver labels, synthetic personas, offline profile).

# Appendix A: generated results (from evals/results/*.json)
