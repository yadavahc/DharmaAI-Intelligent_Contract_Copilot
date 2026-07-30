"""Pydantic request/response models for the API surface."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── identity (supplied by the Next.js server, which owns NextAuth) ──────────
class ActorContext(BaseModel):
    actor_id: str = Field(default="anonymous", max_length=255)
    actor_role: str = Field(default="BUSINESS_USER", max_length=32)


# ── contracts ──────────────────────────────────────────────────────────────
class ContractCreateMeta(ActorContext):
    title: Optional[str] = Field(default=None, max_length=500)
    counterparty: str = Field(default="", max_length=255)


class ReviewRequest(ActorContext):
    include_redline: bool = True
    limit: Optional[int] = Field(default=None, ge=1, le=200)


# ── negotiation ────────────────────────────────────────────────────────────
class NegotiationRequest(ActorContext):
    clause_id: str
    max_rounds: Optional[int] = Field(default=None, ge=1, le=10)
    include_coach: bool = True


# ── playbook ───────────────────────────────────────────────────────────────
class PlaybookRuleIn(BaseModel):
    id: Optional[str] = Field(default=None, max_length=64)
    title: str = Field(min_length=3, max_length=300)
    category: str = Field(default="*", max_length=64)
    rule_type: str = Field(default="forbidden_language", max_length=48)
    operator: str = Field(default="", max_length=8)
    threshold: Optional[float] = None
    keywords: List[str] = Field(default_factory=list)
    severity: str = Field(default="Medium", max_length=16)
    risk_points: int = Field(default=20, ge=0, le=100)
    guidance: str = ""
    preferred_language: str = ""
    active: bool = True


class PlaybookRuleUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=300)
    category: Optional[str] = Field(default=None, max_length=64)
    rule_type: Optional[str] = Field(default=None, max_length=48)
    operator: Optional[str] = Field(default=None, max_length=8)
    threshold: Optional[float] = None
    keywords: Optional[List[str]] = None
    severity: Optional[str] = Field(default=None, max_length=16)
    risk_points: Optional[int] = Field(default=None, ge=0, le=100)
    guidance: Optional[str] = None
    preferred_language: Optional[str] = None
    active: Optional[bool] = None


# ── human review / approval gate ───────────────────────────────────────────
class ReviewDecisionIn(ActorContext):
    decision: str = Field(description="approve | reject | edit | comment")
    note: str = ""
    edited_text: Optional[str] = None


class RollbackRequest(ActorContext):
    version_no: int = Field(ge=1)
    reason: str = ""


# ── risk simulator ─────────────────────────────────────────────────────────
class SimulateRequest(BaseModel):
    clause_text: str = Field(min_length=1, max_length=20000)
    category: Optional[str] = None


class SimulateContractRequest(BaseModel):
    clause_id: str
    clause_text: str = Field(min_length=1, max_length=20000)


# ── search ─────────────────────────────────────────────────────────────────
class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=10, ge=1, le=50)
    category: Optional[str] = None
    contract_id: Optional[str] = None
    risk_level: Optional[str] = None
    scope: str = Field(default="clauses", description="clauses | precedents | negotiations | playbook")


# ── guardrail demo ─────────────────────────────────────────────────────────
class GuardrailTestRequest(BaseModel):
    text: str = Field(default="", max_length=50000)
    guardrail: str = Field(
        default="all",
        description="all | prompt_injection | pii | hallucination | approval_gate",
    )
    agent_output: Optional[Dict[str, Any]] = None
    source_text: Optional[str] = None


# ── coach ──────────────────────────────────────────────────────────────────
class CoachRequest(BaseModel):
    clause_text: str
    category: str = "Other"
    round: int = Field(default=1, ge=1, le=20)
    proposed_redline: str = ""
    current_risk: Optional[float] = None
    history: List[Dict[str, Any]] = Field(default_factory=list)
