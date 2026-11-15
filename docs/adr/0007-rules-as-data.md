# ADR 0007: Rules, thresholds and prompts live in config / files

**Context.** A platform policy change must be absorbable cheaply (change request).

**Decision.** Pricing/Connects caps, compliance banned phrases, min/max lengths, thresholds in `agent/config.yaml`; platform rules fetched from the marketplace `/policy` endpoint at run time; one prompt file per node.

**Consequences.** See report section 6 for the measured diff size of the change request.
