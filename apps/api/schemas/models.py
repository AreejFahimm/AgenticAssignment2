"""Request/response models. The OpenAPI schema generated from these produces the typed TS client (apps/web/src/lib/api)."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Persona = Literal["ai_ml_engineer", "fullstack_web_dev", "data_analyst"]


class RegisterIn(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=128)
    persona: Persona = "ai_ml_engineer"


class LoginIn(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    token: str


class SavedSearch(BaseModel):
    name: str = "Default"
    query: str = ""
    interval_minutes: int = Field(default=240, ge=60, le=1440)   # live mode: never more often than hourly


class SettingsIn(BaseModel):
    hourly_rate: float | None = Field(default=None, gt=0)
    floor: float | None = Field(default=None, ge=0)
    weekly_connects_budget: int = Field(default=60, ge=0, le=1000)
    autonomy: Literal["suggest", "auto_skip_low_fit"] = "suggest"      # there is no auto-send option
    saved_searches: list[SavedSearch] = Field(default_factory=lambda: [SavedSearch()])
    marketplace: Literal["gigsim", "upwork"] = "gigsim"
    persona: Persona | None = None


class MeOut(BaseModel):
    id: str
    email: str
    persona: Persona
    settings: dict[str, Any]


class RunRow(BaseModel):
    thread_id: str
    kind: str
    job_id: str | None = None
    proposal_id: str | None = None
    title: str | None = None
    status: str
    decision: str | None = None
    fit: float | None = None
    risk: float | None = None
    bid: float | None = None
    connects: int | None = None
    category: str | None = None
    tokens: int = 0
    usd: float = 0
    latency_ms: int = 0
    updated: float | None = None
    summary: dict[str, Any] | None = None


class ApprovalIn(BaseModel):
    status: Literal["approved", "edited", "rejected"]
    edited_text: str | None = Field(default=None, max_length=6000)
    reason: str | None = Field(default=None, max_length=500)
    slot_start: str | None = None


class RegenerateIn(BaseModel):
    paragraph_index: int = Field(ge=0)


class RegenerateOut(BaseModel):
    paragraph_index: int
    text: str
    evidence_ids: list[str]


class StatusOut(BaseModel):
    marketplace_ok: bool
    marketplace_error: str | None = None
    queued_degraded: int = 0
    mode: str
    model_profile: str
