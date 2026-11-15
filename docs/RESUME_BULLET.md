# Résumé bullet (draft; every number is in evals/results/)

- Built GigBid, a LangGraph multi-agent freelancer copilot (3 MCP servers, human-approval interrupts, exactly-once submit, React/FastAPI app); ablation-driven RAG shipped at **0.511 Recall@5 vs 0.357 for a naive baseline** (`ablation.json`; labels are rule-derived, so partly circular).
- Evaluated on 10.8k real job posts and ~1.5M price records with CI eval gates; scam recall **1.00 / precision 0.91**, unsupported-claim rate **0.51 → 0.00** on planted fabrications, p95 **0.65 s** per job analysed, 35 pytest + 8 Playwright tests.

Edit to match what you can defend in the viva; remove any number you cannot explain.
