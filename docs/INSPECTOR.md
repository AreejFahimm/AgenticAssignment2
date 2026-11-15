# MCP Inspector screenshots (A7) — you take these

Run each server in the official MCP Inspector and screenshot (1) the tool list with schemas/annotations, (2) one successful call, (3) one rejected call (constraint violation).

```bash
npx @modelcontextprotocol/inspector python -m mcp_servers.portfolio.server
npx @modelcontextprotocol/inspector python -m mcp_servers.marketplace.server      # needs: GIGSIM_INPROCESS=1
npx @modelcontextprotocol/inspector python -m mcp_servers.workspace.server
```
Suggested calls: `search_evidence {"requirement":"docker deployment","k":3}` · `create_proposal_draft` with `dry_run:true` then with a too-short `idempotency_key` (rejected) · `create_tentative_hold`.
Save the PNGs in `docs/images/inspector-*.png` and link them from the report (appendix).
Claude Desktop / Cursor: add `{"command":"python","args":["-m","mcp_servers.portfolio.server"],"env":{"PORTFOLIO_PERSONA":"ai_ml_engineer"}}` to the MCP servers config.
