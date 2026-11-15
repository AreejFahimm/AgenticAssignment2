# ADR 0001: One marketplace port, two adapters

**Context.** Agents must not know whether they talk to GigSim or Upwork, and the live platform forbids scraping/automation outside its official MCP server.

**Decision.** All marketplace access goes through `MarketplacePort`; the Marketplace MCP server is the only caller. GigSim adapter is implemented and tested; the live adapter plugs into `make_marketplace`.

**Consequences.** Switching is one config line; the live adapter is documented but not exercised (no Upwork credentials).
