# AI usage disclosure (DRAFT: review and make it true to your own experience before submitting)

**Tool used:** Claude Code (Claude Sonnet 5.5) generated most of the code in this repository under my direction: data scripts, GigSim-local, MCP servers, RAG variants,
LangGraph graphs, FastAPI, React UI, tests, evals and docs. I remain responsible for all of it and must be able to explain and change it live (viva).

**Tasks the assistant did:** everything above, plus running tests and evaluations and reporting the output.
**Tasks that were mine (must be done by me, not the assistant):** the 30 judge-calibration labels and the blind pairwise panel (`evals/datasets/judge_labels.csv`),
Kaggle licence/attribution review, choosing and recording the shipped design, the demo video, the write-up, deployment credentials, and the Upwork live-mode decision.

## Incorrect suggestions that were identified and corrected (real incidents from development)
1. **Interrupts swallowed by error handling.** The first `guarded()` node wrapper used `except Exception`, which also caught LangGraph's `GraphInterrupt`, so every approval became a
   `dead_letter` state. Found by running the first end-to-end job; fixed by re-raising `GraphBubbleUp`; covered by `test_parallel_branches_interrupt_and_approve`.
2. **Claim detector matched the wrong sentences.** A regex patched in through a shell heredoc contained backspace characters instead of `\b`, so no sentence counted as an experience claim
   and the verifier silently passed everything; later the pattern over-matched ("my attention", "build"). Found by printing verifier labels on real drafts; fixed and re-tested.
3. **Email regex ate the sentence-final period**, so Compliance deleted two sentences instead of one and blocked a valid edit. Found by `test_edit_is_rechecked_by_compliance...`; fixed in `agent/nodes/compliance.py`.
4. **GigSim idempotency keys were global, not per user**, so one user's cached proposal was returned to another user's retry (a real cross-tenant bug in the simulator). Found when the full test suite failed
   while each file passed alone; keys are now scoped by `(user, key)`.
5. **Real job posts end in boilerplate** (`Budget: … Posted On: … Skills: …`) that polluted requirements and drafts; found by reading a drafted proposal; the preprocessor now strips it and keeps the listed skills.

Prompts for the LLM profiles are in `agent/prompts/`; none were tuned on a live model in this repository.
