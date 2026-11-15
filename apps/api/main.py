"""GigBid API (FastAPI). Run: uvicorn apps.api.main:app --port 8000

Env: GIGSIM_INPROCESS=1 (single-process deploy; GigSim-local mounted in memory) | GIGSIM_BASE_URL for a separate GigSim.
"""
from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from agent.checkpoint import make_checkpointer
from agent.security import mask_pii
from apps.api import db
from apps.api.auth import users
from apps.api.routers import analytics, approvals, auth, jobs, messages, proposals, runs
from apps.api.runner import Runner


class PIIFilter(logging.Filter):
    """PII masking in logs (E4): emails, phones, card numbers, bearer tokens never reach log output."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = mask_pii(str(record.msg))
        if record.args:
            record.args = tuple(mask_pii(str(a)) if isinstance(a, str) else a for a in record.args)
        return True


for h in logging.getLogger().handlers + [logging.getLogger("uvicorn.access"), logging.getLogger("uvicorn.error")]:
    h.addFilter(PIIFilter()) if hasattr(h, "addFilter") else None
logging.getLogger().addFilter(PIIFilter())


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.db()
    users.seed_reviewer()
    async with make_checkpointer() as cp:
        app.state.runner = Runner(cp)
        await app.state.runner.recover()                 # continue threads that were mid-run when we last stopped
        app.state.runner.start_health_loop()
        yield
        if app.state.runner._health_task:
            app.state.runner._health_task.cancel()


app = FastAPI(title="GigBid API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(","),
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def trace_id_middleware(request: Request, call_next):
    """One trace id from the UI request on: echoed in responses and passed into runs / MCP calls / audit log."""
    request.state.trace_id = request.headers.get("x-trace-id") or uuid.uuid4().hex[:12]
    resp = await call_next(request)
    resp.headers["x-trace-id"] = request.state.trace_id
    return resp


@app.get("/health")
async def health(request: Request):
    r = getattr(request.app.state, "runner", None)
    return {"status": "ok", "service": "gigbid-api", "marketplace_ok": r.marketplace_ok if r else None}


for router in (auth.router, jobs.router, proposals.router, approvals.router, messages.router, runs.router, analytics.router):
    app.include_router(router)


# Single-container deploy: serve the built web app (hash-routed SPA) from the same origin as the API.
_DIST = Path(__file__).resolve().parents[1] / "web" / "dist"
if _DIST.exists():
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="web")
