"""Arq (Redis) worker settings: same tasks as scheduler.py, run as `arq worker.arq_settings.WorkerSettings`.

NOTE: this path needs a Redis server; it was written for the docker-compose deployment and has NOT been exercised in the
development environment (no Docker/Redis available). The asyncio scheduler in worker/scheduler.py is the tested path.
"""
from __future__ import annotations

import json
import os

from arq import cron
from arq.connections import RedisSettings

from agent.checkpoint import make_checkpointer
from apps.api import db
from apps.api.runner import Runner
from worker.scheduler import scan_due

_LAST: dict[str, float] = {}


async def startup(ctx):
    db.db()
    ctx["cm"] = make_checkpointer()
    cp = await ctx["cm"].__aenter__()
    ctx["runner"] = Runner(cp)
    await ctx["runner"].recover()


async def shutdown(ctx):
    await ctx["cm"].__aexit__(None, None, None)


async def scan_user(ctx, user_id: str) -> int:
    u = db.q1("select id,email,persona,settings from users where id=?", user_id)
    u["settings"] = json.loads(u["settings"])
    return len(await ctx["runner"].scan(u))


async def scan_all(ctx) -> int:
    return await scan_due(ctx["runner"], _LAST)


class WorkerSettings:
    functions = [scan_user]
    cron_jobs = [cron(scan_all, minute=set(range(0, 60, 5)))]   # tick every 5 min; per-user intervals are enforced in scan_due
    on_startup, on_shutdown = startup, shutdown
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    max_jobs = 2
    job_timeout = 300
