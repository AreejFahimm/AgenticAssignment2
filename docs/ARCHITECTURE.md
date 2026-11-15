# Architecture

GigBid is a human-in-the-loop freelancer copilot. Agents find, judge and draft; the freelancer decides. **Nothing is sent, and no
Connects are spent, until a person approves in the web UI** (a LangGraph `interrupt()` that survives restarts).

```
 Web (React/TS, SSE)  ──HTTP──▶  FastAPI  ──▶  Run manager (asyncio worker / scheduler)
                                              │
                          ┌───────────────────┴────────────────────┐
                          ▼                                        ▼
                  Bid graph (1 thread / job)            Conversation graph (1 thread / client conversation)
                          │  all tool use via MCPHub (per-agent allowlists)
        ┌─────────────────┼───────────────────┐
        ▼                 ▼                   ▼
  Portfolio MCP     Marketplace MCP      Workspace MCP        (+ official Upwork MCP, GitHub MCP in live mode)
  (RAG: index+      (wraps ONE port:     (calendar slots,
   variants)        GigSim | Upwork)     email drafts)
```

## The marketplace port (R1)
`agent/marketplace_port.py` defines one `MarketplacePort` protocol and the `GigSimAdapter` (timeouts, bounded retries, backoff, typed errors).
A live Upwork adapter plugs into the same factory (`make_marketplace`, `marketplace.mode` in `agent/config.yaml`). Agents never import an adapter:
they only call MCP tools; the Marketplace MCP server calls the port. Switching GigSim → live changes **config and the adapter module only**.

## Bid graph (C1) — `agent/graphs/bid_graph.py`
Hand-written `StateGraph`. Scout → fan-out with `Send` to **Job Analyst ‖ Risk Assessor ‖ Fit Matcher** → join → decision (skip / watch / bid) →
Pricing → Writer → **claim verification** → Critic (≤ 2 send-backs) → Compliance Guard → prepare dry-run preview → **approval interrupt** → submit.
Graph source (Mermaid, generated from code): [`images/bid_graph.mmd`](images/bid_graph.mmd), conversation graph: [`images/conversation_graph.mmd`](images/conversation_graph.mmd).

## Why each agent exists
| Agent | Why a separate role | Tools |
|---|---|---|
| Scout | cheap, frequent, schedulable; owns dedup so work is idempotent | marketplace read |
| Job Analyst | turns free text into a typed `JobSpec`; the only node that sees raw job text for extraction; no tools (smallest attack surface) | none |
| Risk Assessor | scam / free-work / off-platform / injection flags + client quality; must be able to veto independently of fit | marketplace read |
| Fit Matcher | requirement → evidence matrix; runs the shipped RAG variant through the Portfolio server | portfolio read |
| Pricing Strategist | market statistics (Kaggle price bands), client spend, user floor, Connects ROI | marketplace read |
| Proposal Writer | drafts with evidence ids; applies promoted style rules | portfolio read |
| Claim verifier | splits draft into claims and grounds each one before the Critic sees it (R5) | none |
| Critic | grounding, personalisation, length; bounded loop | portfolio read |
| Compliance Guard | policy pack as data (config + the marketplace's own /policy); strips contact details, guarantees, off-platform asks | none |
| Client Liaison | conversation graph: intent, reply, slots, pipeline | marketplace read/write after approval, workspace |

## State, trace, memory (C2) — kept apart
- **State** (`agent/state.py`): what this thread needs now, with reducers on every field parallel branches can write. Checkpointed (Postgres or SQLite).
- **Execution trace** (`state["trace"]` + `data/processed/traces/<thread>.json` + audit log + optional Langfuse): every node timing, tool call, argument and observation; PII masked. Read-only for audit.
- **Long-term memory** (`agent/memory/`, LangGraph store): **style memory** (from the user's edits) and **outcome memory** (replies/hires per category) written
  only through `promotion_rules.py`. Raw tool output never enters memory. The Settings screen lists and deletes it.

## Durability and exactly-once (C6)
Checkpointer = SQLite file (default) or `AsyncPostgresSaver` when `DATABASE_URL` is postgres. Submit keys are `"<thread_id>:draft"` / `":submit"`, so replays,
double clicks and crash-resumes hit the marketplace's idempotency check; the API also returns 409 on a repeated approval. Tested in
`tests/integration/test_bid_graph.py::test_restart_resumes_and_submits_exactly_once`.

## Failure handling (C7)
Per-node `RetryPolicy`; step and token budgets → `needs_attention`; `MarketplaceDown` → `degraded` state, queued, and re-driven by the health loop;
unrecoverable node errors → `dead_letter`; cheap nodes have a fallback model in config; GigSim 429/5xx handled with bounded backoff in the adapter.

## RAG (B)
`rag/index/store.py` (per-persona index: dense `bge-small-en-v1.5` + BM25, incremental `add_items`), `rag/variants/*` (V0–V4, V8, `best`), `rag/verify.py`.
The index is an in-process NumPy matrix, not a vector database; it is behind `PersonaIndex` so a Qdrant/pgvector backend is a drop-in (not done).

## Deployment
`infra/docker-compose.yml` (api+web, worker, gigsim, three MCP servers, postgres, redis, optional ollama). Open models only; embeddings and reranker run on CPU.
