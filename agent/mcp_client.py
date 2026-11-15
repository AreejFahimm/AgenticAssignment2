"""MCP client hub with PER-AGENT TOOL ALLOWLISTS (A6): each agent sees only the tools it needs, filtered by name.

Backends:
  inprocess (default)  - real MCP protocol over in-memory transport to the three servers (tests, single-container deploy)
  http                 - langchain-mcp-adapters MultiServerMCPClient over Streamable HTTP to separate server processes
                         (docker compose; the official Upwork server is added here in live mode with OAuth headers)

Resilience: per-call timeout, bounded retries with exponential backoff, and a clear degraded-mode exception
(MarketplaceDown) the graph turns into a visible state ("marketplace unavailable, work queued").
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from mcp.shared.memory import create_connected_server_and_client_session as connect

ALLOWLIST: dict[str, set[str]] = {
    "scout": {"marketplace.search_jobs", "marketplace.get_job"},
    "analyst": set(),
    "risk_assessor": {"marketplace.get_client_history"},
    "fit_matcher": {"portfolio.search_evidence", "portfolio.list_skills"},
    "pricing": {"marketplace.get_connects_balance", "marketplace.get_job"},
    "writer": {"portfolio.search_evidence", "portfolio.get_case_study"},
    "critic": {"portfolio.search_evidence"},
    "compliance": set(),
    "client_liaison": {"marketplace.list_messages", "workspace.free_calendar_slots", "workspace.create_tentative_hold",
                       "workspace.create_email_draft"},
    # approval-gated writer nodes: only reachable AFTER interrupt() returns an approval
    "submitter": {"marketplace.create_proposal_draft", "marketplace.submit_proposal", "marketplace.get_job",
                  "marketplace.get_connects_balance"},
    "messenger": {"marketplace.send_message"},
    # orchestrator (not an agent): pipeline sync, policy fetch, health checks
    "system": {"marketplace.list_proposals", "marketplace.get_platform_policy", "marketplace.get_connects_balance", "marketplace.search_jobs",
               "marketplace.get_job", "marketplace.list_messages"},
}


class MarketplaceDown(Exception):
    """Marketplace MCP unreachable after bounded retries -> degraded mode."""


class ToolDenied(PermissionError):
    pass


def _servers():
    from mcp_servers.marketplace import server as market
    from mcp_servers.portfolio import server as portfolio
    from mcp_servers.workspace import server as workspace
    return {"portfolio": portfolio, "marketplace": market, "workspace": workspace}


def _payload(res) -> Any:
    if res.structuredContent is not None:
        return res.structuredContent
    return json.loads(res.content[0].text) if res.content else None


class MCPHub:
    def __init__(self, timeout: float = 30.0, retries: int = 2, backoff: float = 0.4, backend: str | None = None):
        self.timeout, self.retries, self.backoff = timeout, retries, backoff
        self.backend = backend or os.getenv("MCP_BACKEND", "inprocess")
        self.calls: list[dict] = []  # execution TRACE (tool, args, observation) for audit

    async def call(self, agent: str, tool: str, args: dict, *, user: str = "local-user", persona: str | None = None,
                   trace_id: str = "", retries_override: int | None = None) -> Any:
        if tool not in ALLOWLIST.get(agent, set()):
            raise ToolDenied(f"agent {agent!r} may not call {tool!r}")
        last: Exception | None = None
        retries = self.retries if retries_override is None else retries_override
        for attempt in range(retries + 1):
            try:
                out = await asyncio.wait_for(self._once(tool, args, user, persona, trace_id), self.timeout)
                self.calls.append(dict(agent=agent, tool=tool, args=args, ok=True, trace_id=trace_id))
                del self.calls[:-5000]
                return out
            except ToolDenied:
                raise
            except Exception as e:  # noqa: BLE001
                last = e
                transient = "UNAVAILABLE" in str(e) or isinstance(e, asyncio.TimeoutError)
                self.calls.append(dict(agent=agent, tool=tool, args=args, ok=False, error=str(e)[:200], trace_id=trace_id))
                if not transient:
                    raise
                await asyncio.sleep(self.backoff * 2 ** attempt)
        if tool.startswith("marketplace."):
            raise MarketplaceDown(str(last)) from last
        raise RuntimeError(f"tool {tool} failed: {last}")

    async def _once(self, tool: str, args: dict, user: str, persona: str | None, trace_id: str) -> Any:
        server_name, name = tool.split(".", 1)
        if self.backend == "http":
            return await self._http(server_name, name, args, user, trace_id)
        mods = _servers()
        mods["marketplace"].current_user.set(user)
        mods["marketplace"].current_trace.set(trace_id)
        mods["portfolio"].current_persona.set(persona)
        async with connect(mods[server_name].mcp._mcp_server) as c:
            res = await c.call_tool(name, args)
        if res.isError:
            raise RuntimeError(res.content[0].text if res.content else "tool error")
        return _payload(res)

    async def _http(self, server_name: str, name: str, args: dict, user: str, trace_id: str) -> Any:
        from langchain_mcp_adapters.client import MultiServerMCPClient
        urls = {"portfolio": os.getenv("PORTFOLIO_MCP_URL", "http://localhost:9101/mcp"),
                "marketplace": os.getenv("MARKETPLACE_MCP_URL", "http://localhost:9102/mcp"),
                "workspace": os.getenv("WORKSPACE_MCP_URL", "http://localhost:9103/mcp")}
        hdr = {"Authorization": f"Bearer {os.getenv('MARKETPLACE_MCP_TOKEN', user)}", "x-trace-id": trace_id}
        client = MultiServerMCPClient({server_name: {"url": urls[server_name], "transport": "streamable_http", "headers": hdr}})
        tools = {t.name: t for t in await client.get_tools()}
        res = await tools[name].ainvoke(args)
        return json.loads(res) if isinstance(res, str) else res
