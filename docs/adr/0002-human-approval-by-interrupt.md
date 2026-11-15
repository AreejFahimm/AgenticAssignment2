# ADR 0002: Approval is a LangGraph interrupt, not a prompt rule

**Context.** Prompts can be talked out of rules; a hard graph edge cannot.

**Decision.** `submit`/`send` nodes are reachable only through the `approval` node, which calls `interrupt()`. Autonomy settings can auto-skip but there is no auto-send option anywhere.

**Consequences.** Approvals survive restarts (checkpointer) and the API returns 409 on repeated approval. Cost: each job holds a paused thread.
