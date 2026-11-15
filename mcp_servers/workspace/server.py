"""Workspace MCP server (A3): free calendar slots, tentative interview holds, email drafts.

Local mock backend (JSON files in data/processed/workspace/). Swap `Backend` for Google Calendar/Gmail
(official APIs) without changing the tools: the agent only ever sees MCP tools.
Nothing here sends email: it only creates DRAFTS and TENTATIVE holds.
"""
from __future__ import annotations

import argparse
import json
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

STORE = Path(os.getenv("WORKSPACE_DIR", Path(__file__).resolve().parents[2] / "data" / "processed" / "workspace"))
mcp = FastMCP("gigbid-workspace")
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)


class Slot(BaseModel):
    start: str
    end: str


class SlotList(BaseModel):
    timezone: str = "UTC"
    slots: list[Slot]


class Hold(BaseModel):
    hold_id: str
    status: str = "tentative"
    start: str
    end: str
    title: str


class EmailDraft(BaseModel):
    draft_id: str
    to: str
    subject: str
    body: str
    status: str = "draft"


def _load(name: str) -> dict:
    f = STORE / f"{name}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def _save(name: str, data: dict) -> None:
    STORE.mkdir(parents=True, exist_ok=True)
    (STORE / f"{name}.json").write_text(json.dumps(data, indent=2), encoding="utf-8")


@mcp.tool(annotations=READ, description="List free 30-minute interview slots in the next N days (09:00-17:00 UTC weekdays, minus holds).")
def free_calendar_slots(days: Annotated[int, Field(ge=1, le=14)] = 5, duration_minutes: Annotated[int, Field(ge=15, le=120)] = 30,
                        from_iso: str | None = None) -> SlotList:
    start = datetime.fromisoformat(from_iso) if from_iso else datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    busy = {(h["start"]) for h in _load("holds").values()}
    out: list[Slot] = []
    d = start
    for _ in range(days * 24):
        d += timedelta(hours=1)
        if d.weekday() < 5 and 9 <= d.hour < 17 and d > start:
            iso = d.isoformat(timespec="minutes")
            if iso not in busy:
                out.append(Slot(start=iso, end=(d + timedelta(minutes=duration_minutes)).isoformat(timespec="minutes")))
    return SlotList(slots=out[:8])


@mcp.tool(annotations=WRITE, description="Create a TENTATIVE calendar hold for an interview. Does not invite anyone.")
def create_tentative_hold(start_iso: str, title: Annotated[str, Field(min_length=1, max_length=120)],
                          duration_minutes: Annotated[int, Field(ge=15, le=120)] = 30,
                          idempotency_key: Annotated[str, Field(min_length=8, max_length=64)] = "") -> Hold:
    holds = _load("holds")
    key = idempotency_key or f"{start_iso}|{title}"
    if key in holds:
        return Hold(**holds[key])
    start = datetime.fromisoformat(start_iso)
    h = Hold(hold_id="hold-" + uuid.uuid4().hex[:8], start=start_iso,
             end=(start + timedelta(minutes=duration_minutes)).isoformat(timespec="minutes"), title=title)
    holds[key] = h.model_dump()
    _save("holds", holds)
    return h


@mcp.tool(annotations=WRITE, description="Create an email DRAFT (never sends). The user reviews and sends it themselves.")
def create_email_draft(to: Annotated[str, Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")],
                       subject: Annotated[str, Field(min_length=1, max_length=200)],
                       body: Annotated[str, Field(min_length=1, max_length=8000)],
                       idempotency_key: Annotated[str, Field(min_length=8, max_length=64)] = "") -> EmailDraft:
    drafts = _load("drafts")
    key = idempotency_key or f"{to}|{subject}"
    if key in drafts:
        return EmailDraft(**drafts[key])
    d = EmailDraft(draft_id="draft-" + uuid.uuid4().hex[:8], to=to, subject=subject, body=body)
    drafts[key] = d.model_dump()
    _save("drafts", drafts)
    return d


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--http", action="store_true")
    ap.add_argument("--port", type=int, default=9103)
    a = ap.parse_args()
    if a.http:
        mcp.settings.port = a.port
        mcp.run(transport="streamable-http")
    else:
        mcp.run()
