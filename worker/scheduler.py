"""Background worker (E1): scheduled scouting and long agent runs execute HERE, never inside a web request.

Two entry points sharing the same functions:
  * `python -m worker.scheduler`   asyncio scheduler (no Redis needed): every user's saved searches on their own interval
  * `worker/arq_settings.py`       the same tasks as Arq jobs on Redis (docker compose), `arq worker.arq_settings.WorkerSettings`

Idempotency: thread id = "<user>.<job_id>" and Scout's SeenStore, so a worker restart never double-analyses a job; the submit
step uses deterministic idempotency keys, so it can never double-submit or double-spend Connects.
Politeness: interval is >= 60 minutes per saved search (validated in the API), bounded concurrency, <= `limit` jobs per scan,
no polling that looks like scraping (live mode default is 240 min, see docs/RUNBOOK.md).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time

from agent.checkpoint import make_checkpointer
from apps.api import db
from apps.api.runner import Runner

log = logging.getLogger("gigbid.worker")
MIN_INTERVAL_MIN = 60


def _users() -> list[dict]:
    out = []
    for u in db.q("select id,email,persona,settings from users"):
        u["settings"] = json.loads(u["settings"])
        out.append(u)
    return out


async def scan_due(runner: Runner, last_run: dict[str, float], now: float | None = None) -> int:
    """Scan every user whose saved-search interval has elapsed. Returns the number of jobs queued."""
    now = now or time.time()
    queued = 0
    for u in _users():
        searches = u["settings"].get("saved_searches", [])
        if not searches:
            continue
        interval = max(min(int(s.get("interval_minutes", 240)) for s in searches), MIN_INTERVAL_MIN) * 60
        if now - last_run.get(u["id"], 0) >= interval:
            last_run[u["id"]] = now
            queued += len(await runner.scan(u))
    return queued


async def main(tick_seconds: int = 60) -> None:
    db.db()
    async with make_checkpointer() as cp:
        runner = Runner(cp)
        await runner.recover()
        runner.start_health_loop()
        last: dict[str, float] = {}
        while True:
            try:
                n = await scan_due(runner, last)
                if n:
                    log.info("queued %d jobs", n)
            except Exception:  # noqa: BLE001 the scheduler must not die on one bad tick
                log.exception("scan tick failed")
            await asyncio.sleep(tick_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
