# ADR 0003: Offline deterministic profile next to open-model profiles

**Context.** Students must run end to end without paying; CI and graders have no GPU; LLM-judged numbers need a calibrated judge.

**Decision.** `models.profile: offline` uses deterministic heuristics per node; `open`/`paid` call any OpenAI-compatible endpoint with per-node models in config. Embeddings and reranker are open CPU models in all profiles.

**Consequences.** All committed measurements are offline-profile numbers. LLM-profile results are NOT measured. Offline quality (extractive writer) is a floor, not the ceiling.
