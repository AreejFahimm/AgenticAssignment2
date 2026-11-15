"""Observability (E3): ONE trace id from UI request -> API -> graph -> every MCP server -> audit log.

Always writes a self-contained JSON trace per thread to data/processed/traces/<thread>.json (node timings, tool calls,
tokens and USD per node) and serves it at GET /runs/{thread}/trace, so a reviewer can open a trace with zero setup.
If LANGFUSE_* env vars are set, `callbacks()` returns the Langfuse handler so the same runs also appear there.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from agent import llm
from agent.config import ROOT
from agent.security import mask_pii

TRACE_DIR = ROOT / "data" / "processed" / "traces"


def callbacks() -> list:
    if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
        try:
            from langfuse.langchain import CallbackHandler
            return [CallbackHandler()]
        except Exception:  # noqa: BLE001  tracing must never break a run
            return []
    return []


def write_trace(thread_id: str, trace_id: str, values: dict, tool_calls: list[dict]) -> Path:
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    rec = dict(thread_id=thread_id, trace_id=trace_id, status=values.get("status"), decision=values.get("decision"),
               nodes=values.get("trace", []), tool_calls=[c for c in tool_calls if c.get("trace_id") == trace_id],
               usage_per_node=llm.usage_snapshot(), errors=values.get("errors", []),
               total_ms=sum(n.get("ms", 0) for n in values.get("trace", [])))
    safe = json.loads(mask_pii(json.dumps(rec, default=str)))  # PII masked in traces
    p = TRACE_DIR / (thread_id.replace(":", "_").replace("/", "_") + ".json")
    p.write_text(json.dumps(safe, indent=2), encoding="utf-8")
    return p


def read_trace(thread_id: str) -> dict | None:
    p = TRACE_DIR / (thread_id.replace(":", "_").replace("/", "_") + ".json")
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
