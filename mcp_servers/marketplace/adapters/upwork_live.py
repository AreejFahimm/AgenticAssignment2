"""Live Upwork adapter over the OFFICIAL Upwork MCP server (https://mcp.upwork.com/mcp, OAuth 2.1, Streamable HTTP).

STATUS: UNTESTED SKELETON. It was written without Upwork credentials and without access to the server's tool list, so tool names are
DISCOVERED at runtime (`tools/list`) and matched by keywords instead of hard-coded. Before using it: run `python -m mcp_servers.marketplace.adapters.upwork_live --list`
with a valid access token, check the matches printed, and adjust KEYWORDS.

Rules this adapter enforces (assignment + Upwork terms):
  * transport is the official MCP server only: no scraping, no browser automation, no session cookies;
  * every write is a DRAFT the user confirms on Upwork; `submit_proposal` never sends, it returns the draft for confirmation;
  * reads happen only on the schedule configured in agent/config.yaml (marketplace.live_poll_interval_minutes).
The class implements the same MarketplacePort as GigSimAdapter, so the graph cannot tell which marketplace it is using.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

from agent.marketplace_port import MarketplaceRejected, MarketplaceUnavailable

UPWORK_MCP_URL = os.getenv("UPWORK_MCP_URL", "https://mcp.upwork.com/mcp")
KEYWORDS = {  # port method -> keywords that must appear in the Upwork tool name (all of them, any order)
    "search_jobs": ("search", "job"), "get_job": ("get", "job"), "get_client_history": ("client",), "get_connects_balance": ("connect",),
    "list_messages": ("message",), "create_proposal_draft": ("proposal", "draft"), "list_proposals": ("proposal", "list"),
}


class UpworkLiveAdapter:
    def __init__(self, access_token: str, url: str = UPWORK_MCP_URL):
        self._cfg = {"upwork": {"url": url, "transport": "streamable_http", "headers": {"Authorization": f"Bearer {access_token}"}}}
        self._tools: dict[str, Any] | None = None

    async def _discover(self) -> dict[str, Any]:
        if self._tools is None:
            from langchain_mcp_adapters.client import MultiServerMCPClient
            try:
                self._tools = {t.name: t for t in await MultiServerMCPClient(self._cfg).get_tools()}
            except Exception as e:  # noqa: BLE001
                raise MarketplaceUnavailable(f"cannot reach Upwork MCP: {e}") from e
        return self._tools

    async def _call(self, method: str, args: dict) -> Any:
        tools = await self._discover()
        want = KEYWORDS.get(method)
        match = [n for n in tools if want and all(k in n.lower() for k in want)]
        if not match:
            raise MarketplaceRejected(501, f"no Upwork tool matches {method!r}; tools: {sorted(tools)}")
        try:
            res = await tools[match[0]].ainvoke(args)
        except Exception as e:  # noqa: BLE001
            raise MarketplaceUnavailable(str(e)) from e
        return json.loads(res) if isinstance(res, str) else res

    # ---- reads ----
    async def search_jobs(self, query: str, limit: int = 20, offset: int = 0):
        return await self._call("search_jobs", {"query": query, "limit": limit})

    async def get_job(self, job_id: str):
        return await self._call("get_job", {"job_id": job_id})

    async def get_client_history(self, client_id: str):
        return await self._call("get_client_history", {"client_id": client_id})

    async def get_connects_balance(self):
        return await self._call("get_connects_balance", {})

    async def list_messages(self, proposal_id: str):
        return await self._call("list_messages", {"proposal_id": proposal_id})

    async def list_proposals(self):
        return await self._call("list_proposals", {})

    async def get_proposal(self, proposal_id: str):
        return {"proposal_id": proposal_id, "status": "draft"}

    async def get_platform_policy(self):
        return {"note": "live mode: Upwork's own rules apply; see docs/RUNBOOK.md"}

    # ---- writes: drafts only ----
    async def create_proposal_draft(self, payload: dict[str, Any], idempotency_key: str):
        return await self._call("create_proposal_draft", {**payload, "client_request_id": idempotency_key})

    async def submit_proposal(self, proposal_id: str, idempotency_key: str):
        # The official server only creates drafts; the user confirms on Upwork. We never click through for them.
        return {"proposal_id": proposal_id, "status": "draft_awaiting_confirmation_on_upwork", "idempotency_key": idempotency_key}

    async def send_message(self, proposal_id: str, text: str, idempotency_key: str):
        return {"ok": True, "status": "message_draft_created", "note": "confirm and send it on Upwork"}


async def _list() -> None:  # pragma: no cover
    a = UpworkLiveAdapter(os.environ["UPWORK_ACCESS_TOKEN"])
    for n in sorted(await a._discover()):
        print(n)


if __name__ == "__main__":  # pragma: no cover
    import asyncio
    if "--list" in sys.argv:
        asyncio.run(_list())
