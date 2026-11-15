# ADR 0005: Verify claims before the Critic

**Context.** R5: no unsupported experience claims may reach the user.

**Decision.** Draft -> claim splitter -> grounding check against retrieved evidence (token overlap + number agreement) -> unsupported claims removed -> Critic.

**Consequences.** Deterministic and explainable; weaker than an LLM judge on paraphrases; its false-positive/recall are measured with planted fabrications (`verify_eval`).
