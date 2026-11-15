"""The ONE marketplace interface (requirement R1). Agents and MCP servers depend only on this.

Adapters: GigSimAdapter (here) and UpworkLiveAdapter (mcp_servers/marketplace/adapters/upwork_live.py,
to be written). Switching is done by `marketplace.mode` in agent/config.yaml, never in agent code.
"""
from __future__ import annotations

import asyncio
from typing import Any, Protocol

import httpx


class MarketplaceUnavailable(Exception):
    """Raised after bounded retries fail (5xx / timeouts / connection refused). The UI shows degraded mode."""


class MarketplaceRejected(Exception):
    """A 4xx the caller must handle (e.g. 402 insufficient Connects, 422 policy violation)."""

    def __init__(self, status: int, detail: str):
        super().__init__(f"{status}: {detail}")
        self.status, self.detail = status, detail


class MarketplacePort(Protocol):
    async def search_jobs(self, query: str, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]: ...
    async def get_job(self, job_id: str) -> dict[str, Any]: ...
    async def get_client_history(self, client_id: str) -> dict[str, Any]: ...
    async def get_connects_balance(self) -> dict[str, Any]: ...
    async def list_messages(self, proposal_id: str) -> list[dict[str, Any]]: ...
    async def get_proposal(self, proposal_id: str) -> dict[str, Any]: ...
    async def list_proposals(self) -> list[dict[str, Any]]: ...
    async def get_platform_policy(self) -> dict[str, Any]: ...
    async def create_proposal_draft(self, payload: dict[str, Any], idempotency_key: str) -> dict[str, Any]: ...
    async def submit_proposal(self, proposal_id: str, idempotency_key: str) -> dict[str, Any]: ...
    async def send_message(self, proposal_id: str, text: str, idempotency_key: str) -> dict[str, Any]: ...


class GigSimAdapter:
    """GigSim REST adapter with timeouts, bounded retries and exponential backoff.

    Retries on 429 / 5xx / transport errors only (writes are safe to retry because every write
    carries an idempotency key that GigSim de-duplicates)."""

    def __init__(self, base_url: str, token: str, *, timeout: float = 10.0, max_retries: int = 3,
                 backoff: float = 0.3, transport: httpx.AsyncBaseTransport | None = None):
        self._c = httpx.AsyncClient(base_url=base_url, timeout=timeout, transport=transport,
                                    headers={"Authorization": f"Bearer {token}"})
        self._retries, self._backoff = max_retries, backoff

    async def aclose(self) -> None:
        await self._c.aclose()

    async def _req(self, method: str, url: str, **kw) -> Any:
        last: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                r = await self._c.request(method, url, **kw)
            except (httpx.TransportError, httpx.TimeoutException) as e:
                last = e
            else:
                if r.status_code == 429 or r.status_code >= 500:
                    last = MarketplaceUnavailable(f"{r.status_code} from marketplace")
                    wait = float(r.headers.get("Retry-After", 0) or 0)
                    await asyncio.sleep(min(wait, 2.0))
                elif r.status_code >= 400:
                    raise MarketplaceRejected(r.status_code, r.json().get("detail", r.text) if r.content else "")
                else:
                    return r.json()
            await asyncio.sleep(self._backoff * (2 ** attempt))
        raise MarketplaceUnavailable(str(last))

    async def search_jobs(self, query: str, limit: int = 20, offset: int = 0):
        return (await self._req("GET", "/jobs", params={"q": query, "limit": limit, "offset": offset}))["jobs"]

    async def get_job(self, job_id: str):
        return await self._req("GET", f"/jobs/{job_id}")

    async def get_client_history(self, client_id: str):
        return await self._req("GET", f"/clients/{client_id}/history")

    async def get_connects_balance(self):
        return await self._req("GET", "/connects/balance")

    async def list_proposals(self):
        return await self._req("GET", "/proposals")

    async def get_platform_policy(self):
        return await self._req("GET", "/policy")

    async def get_proposal(self, proposal_id: str):
        return await self._req("GET", f"/proposals/{proposal_id}")

    async def list_messages(self, proposal_id: str):
        return await self._req("GET", "/messages", params={"proposal_id": proposal_id})

    async def create_proposal_draft(self, payload: dict[str, Any], idempotency_key: str):
        return await self._req("POST", "/proposals", json={**payload, "idempotency_key": idempotency_key})

    async def submit_proposal(self, proposal_id: str, idempotency_key: str):
        return await self._req("POST", f"/proposals/{proposal_id}/submit", json={"idempotency_key": idempotency_key})

    async def send_message(self, proposal_id: str, text: str, idempotency_key: str):
        return await self._req("POST", "/messages", json={"proposal_id": proposal_id, "text": text,
                                                         "idempotency_key": idempotency_key})


def make_marketplace(config: dict[str, Any], *, base_url: str, token: str, **kw) -> MarketplacePort:
    """Factory driven by config (marketplace.mode). Live Upwork adapter is wired here when written."""
    mode = config.get("marketplace", {}).get("mode", "gigsim")
    if mode == "gigsim":
        return GigSimAdapter(base_url, token, **kw)
    if mode == "upwork_live":  # UNTESTED: see mcp_servers/marketplace/adapters/upwork_live.py
        from mcp_servers.marketplace.adapters.upwork_live import UpworkLiveAdapter
        return UpworkLiveAdapter(token)
    raise NotImplementedError(f"unknown marketplace mode {mode!r}")
