# ADR 0006: State, trace and long-term memory are separate stores

**Context.** Mixing raw tool output into memory poisons future decisions; mixing trace into state bloats checkpoints.

**Decision.** State in the checkpointer, trace in JSON + audit log, memory only via `promotion_rules.py` (style: >=2 occurrences on >=2 jobs; outcome: >=3 samples per category).

**Consequences.** User can see and delete memory in Settings.
