# ADR 0004: RAG variant chosen by evaluation

**Context.** Spec R6 forbids default choices.

**Decision.** Variants V0-V4, V8 and a composite `best` are config-selectable (`rag.variant`); the shipped one is whichever wins the ablation/latency trade-off in `evals/results/` (see README).

**Consequences.** Gold labels are silver (skill-overlap rules), so the numbers favour lexical-skill matching; reported as a limitation.
