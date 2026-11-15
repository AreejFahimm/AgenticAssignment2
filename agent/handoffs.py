"""Typed hand-offs between agents (C3). Anything a later step decides on is a Pydantic object, never free text."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class JobSpec(BaseModel):
    job_id: str
    title: str
    deliverables: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list, description="atomic requirements, one retrieval each")
    budget_type: Literal["fixed", "hourly", "unknown"] = "unknown"
    budget_min: float | None = None
    budget_max: float | None = None
    timeline_days: int | None = None
    screening_questions: list[str] = Field(default_factory=list)
    hidden_needs: list[str] = Field(default_factory=list)
    category: str | None = None


class RiskReport(BaseModel):
    score: float = Field(ge=0, le=1)
    flags: list[str] = Field(default_factory=list)
    explanation: str = ""
    scam: bool = False
    injection_detected: bool = False
    client_quality: float = Field(default=0.5, ge=0, le=1)


class RequirementMatch(BaseModel):
    requirement: str
    evidence_ids: list[str] = Field(default_factory=list)
    strength: float = Field(default=0.0, ge=0, le=1)


class FitReport(BaseModel):
    score: float = Field(ge=0, le=1)
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    matrix: list[RequirementMatch] = Field(default_factory=list)
    refused: bool = False
    reasons: list[str] = Field(default_factory=list)


class BidDecision(BaseModel):
    action: Literal["skip", "watch", "bid"]
    reasons: list[str] = Field(default_factory=list)
    fit_score: float = 0.0
    risk_score: float = 0.0


class PriceQuote(BaseModel):
    bid_amount: float = Field(gt=0)
    currency: str = "USD"
    band_low: float | None = None
    band_high: float | None = None
    connects_cost: int = 0
    worth_connects: bool = True
    rationale: str = ""


class Claim(BaseModel):
    text: str
    evidence_ids: list[str] = Field(default_factory=list)
    label: str = "supported"


class ProposalDraft(BaseModel):
    job_id: str
    cover_letter: str
    screening_answers: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    revision: int = 0
    status: str = "pending_review"


class Critique(BaseModel):
    passed: bool
    issues: list[str] = Field(default_factory=list)
    revision_requested: bool = False


class ComplianceVerdict(BaseModel):
    passed: bool
    blocked: bool = False
    violations: list[str] = Field(default_factory=list)
    cleaned_text: str = ""
    reason: str = ""
