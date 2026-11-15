"""Checkpointer factory (C6): Postgres when DATABASE_URL is a postgres URL (docker compose / production),
otherwise a local SQLite file so the project runs with zero setup. Same LangGraph API either way."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from agent.config import ROOT


@asynccontextmanager
async def make_checkpointer(path: str | None = None):
    url = os.getenv("DATABASE_URL", "")
    if url.startswith("postgres"):
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        async with AsyncPostgresSaver.from_conn_string(url.replace("+psycopg", "")) as saver:
            await saver.setup()
            yield saver
    else:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        p = path or os.getenv("CHECKPOINT_DB") or str(ROOT / "data" / "processed" / "checkpoints.sqlite")
        async with AsyncSqliteSaver.from_conn_string(p) as saver:
            await saver.setup()
            yield saver
