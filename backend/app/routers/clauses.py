"""Clause endpoints: detail, version history, rollback, risk simulator, precedents."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.agents.heuristics import aggregate_contract_risk, score_clause_heuristic
from app.config import settings
from app.db import Clause, ClauseVersion, Contract, session_scope
from app.domain import ActorType, ClauseCategory, risk_level_for_score
from app.schemas import RollbackRequest, SimulateContractRequest, SimulateRequest
from app.services import audit
from app.services.qdrant_store import find_similar_clauses, recall_precedents
from app.services.seed import get_active_rules

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/clauses", tags=["clauses"])


@router.get("/categories")
def categories() -> Dict[str, Any]:
    return {"categories": ClauseCategory.values()}


@router.get("/{clause_id}")
def get_clause(clause_id: str) -> Dict[str, Any]:
    with session_scope() as session:
        clause = session.get(Clause, clause_id)
        if clause is None:
            raise HTTPException(status_code=404, detail="Clause not found")
        contract = session.get(Contract, clause.contract_id)
        versions = (
            session.execute(
                select(ClauseVersion)
                .where(ClauseVersion.clause_id == clause_id)
                .order_by(ClauseVersion.version_no)
            )
            .scalars()
            .all()
        )
        return {
            "id": clause.id,
            "contract_id": clause.contract_id,
            "contract_title": contract.title if contract else "",
            "index": clause.index,
            "label": clause.label,
            "heading": clause.heading,
            "text": clause.text,
            "category": clause.category,
            "confidence": clause.confidence,
            "risk_score": clause.risk_score,
            "risk_level": clause.risk_level,
            "explanation": clause.explanation,
            "suggested_fix": clause.suggested_fix,
            "classification": clause.classification or {},
            "playbook": clause.playbook or {},
            "risk": clause.risk or {},
            "redline": clause.redline or {},
            "escalation": clause.escalation or {},
            "guardrails": clause.guardrails or {},
            "agent_trace": clause.agent_trace or [],
            "approval_state": clause.approval_state,
            "current_version": clause.current_version,
            "versions": [_version_dict(v) for v in versions],
        }


def _version_dict(v: ClauseVersion) -> Dict[str, Any]:
    return {
        "id": v.id,
        "version_no": v.version_no,
        "text": v.text,
        "source": v.source,
        "author": v.author,
        "author_role": v.author_role,
        "reason": v.reason,
        "risk_score": v.risk_score,
        "risk_level": v.risk_level,
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }


@router.get("/{clause_id}/versions")
def clause_versions(clause_id: str) -> Dict[str, Any]:
    """Version history for the visual diff / rollback UI."""
    with session_scope() as session:
        clause = session.get(Clause, clause_id)
        if clause is None:
            raise HTTPException(status_code=404, detail="Clause not found")
        versions = (
            session.execute(
                select(ClauseVersion)
                .where(ClauseVersion.clause_id == clause_id)
                .order_by(ClauseVersion.version_no)
            )
            .scalars()
            .all()
        )
        return {
            "clause_id": clause_id,
            "current_version": clause.current_version,
            "current_text": clause.text,
            "versions": [_version_dict(v) for v in versions],
        }


@router.post("/{clause_id}/rollback")
def rollback_clause(clause_id: str, body: RollbackRequest) -> Dict[str, Any]:
    """Restore an earlier version.

    Rollback appends a new version rather than deleting history, so the audit
    trail keeps showing that a rollback happened and what it reverted from.
    """
    if body.actor_role not in ("REVIEWER", "ADMIN"):
        raise HTTPException(
            status_code=403,
            detail=f"Role '{body.actor_role}' may not roll back clauses.",
        )

    with session_scope() as session:
        clause = session.get(Clause, clause_id)
        if clause is None:
            raise HTTPException(status_code=404, detail="Clause not found")

        target = session.execute(
            select(ClauseVersion).where(
                ClauseVersion.clause_id == clause_id,
                ClauseVersion.version_no == body.version_no,
            )
        ).scalar_one_or_none()
        if target is None:
            raise HTTPException(
                status_code=404, detail=f"Version {body.version_no} not found"
            )

        previous_text = clause.text
        previous_version = clause.current_version
        new_version_no = clause.current_version + 1

        session.add(
            ClauseVersion(
                id=str(uuid.uuid4()),
                clause_id=clause_id,
                contract_id=clause.contract_id,
                version_no=new_version_no,
                text=target.text,
                source="rollback",
                author=body.actor_id,
                author_role=body.actor_role,
                reason=(
                    body.reason
                    or f"Rolled back to version {body.version_no} from version {previous_version}."
                ),
                risk_score=target.risk_score,
                risk_level=target.risk_level,
            )
        )
        clause.text = target.text
        clause.current_version = new_version_no
        contract_id = clause.contract_id
        heading = clause.heading

    audit.record(
        event_type="clause.rolled_back",
        object_type="clause",
        object_id=clause_id,
        contract_id=contract_id,
        actor_type=ActorType.HUMAN.value,
        actor_id=body.actor_id,
        actor_role=body.actor_role,
        summary=(
            f"{body.actor_id} rolled clause '{heading}' back to version "
            f"{body.version_no} (now version {new_version_no})."
        ),
        payload={
            "restored_version": body.version_no,
            "new_version": new_version_no,
            "reason": body.reason,
            "previous_text_preview": previous_text[:300],
        },
    )
    return {
        "clause_id": clause_id,
        "restored_version": body.version_no,
        "current_version": new_version_no,
        "text": target.text,
    }


@router.post("/simulate")
def simulate_clause_risk(body: SimulateRequest) -> Dict[str, Any]:
    """Feature 2 — Clause Risk Simulator (single clause).

    Deterministic on purpose: the Monaco editor recomputes on every keystroke, so
    scoring must be instant, free, and stable. An LLM call per keystroke would be
    slow, expensive, and would make the score jitter on identical input.
    """
    from app.agents.heuristics import classify_clause_heuristic

    category = body.category
    classification = None
    if not category:
        classification = classify_clause_heuristic(body.clause_text)
        category = classification.category

    result = score_clause_heuristic(
        body.clause_text,
        category,
        get_active_rules(),
        high_threshold=settings.risk_high_threshold,
        medium_threshold=settings.risk_medium_threshold,
    )
    return {
        "category": category,
        "detected_category": classification.category if classification else None,
        "classification_confidence": (
            round(classification.confidence, 3) if classification else None
        ),
        "risk_score": round(result.score, 1),
        "risk_level": result.level,
        "rationale": result.rationale,
        "findings": [f.to_dict() for f in result.findings],
        "triggered_rule_ids": result.triggered_rule_ids,
        "method": "deterministic",
    }


@router.post("/simulate/contract/{contract_id}")
def simulate_contract_risk(contract_id: str, body: SimulateContractRequest) -> Dict[str, Any]:
    """Feature 2 — recompute *whole-contract* risk with one clause edited.

    Returns before/after for both the clause and the contract, which is the delta
    the simulator renders inline.
    """
    rules = get_active_rules()

    with session_scope() as session:
        contract = session.get(Contract, contract_id)
        if contract is None:
            raise HTTPException(status_code=404, detail="Contract not found")

        clauses = (
            session.execute(
                select(Clause).where(Clause.contract_id == contract_id).order_by(Clause.index)
            )
            .scalars()
            .all()
        )
        if not clauses:
            raise HTTPException(status_code=400, detail="Contract has no clauses")

        target = next((c for c in clauses if c.id == body.clause_id), None)
        if target is None:
            raise HTTPException(status_code=404, detail="Clause not found in this contract")

        baseline_scores = [
            {"clause_id": c.id, "category": c.category, "score": c.risk_score, "level": c.risk_level}
            for c in clauses
        ]
        target_category = target.category
        target_before = {"score": target.risk_score, "level": target.risk_level}

    simulated = score_clause_heuristic(
        body.clause_text,
        target_category,
        rules,
        high_threshold=settings.risk_high_threshold,
        medium_threshold=settings.risk_medium_threshold,
    )

    projected_scores = [
        {
            **entry,
            **(
                {"score": simulated.score, "level": simulated.level}
                if entry["clause_id"] == body.clause_id
                else {}
            ),
        }
        for entry in baseline_scores
    ]

    before = aggregate_contract_risk(
        baseline_scores,
        high_threshold=settings.risk_high_threshold,
        medium_threshold=settings.risk_medium_threshold,
    )
    after = aggregate_contract_risk(
        projected_scores,
        high_threshold=settings.risk_high_threshold,
        medium_threshold=settings.risk_medium_threshold,
    )

    return {
        "contract_id": contract_id,
        "clause_id": body.clause_id,
        "category": target_category,
        "clause": {
            "before": target_before,
            "after": {"score": round(simulated.score, 1), "level": simulated.level},
            "delta": round(simulated.score - float(target_before["score"] or 0), 1),
            "rationale": simulated.rationale,
            "findings": [f.to_dict() for f in simulated.findings],
        },
        "contract": {
            "before": before,
            "after": after,
            "delta": round(float(after["score"]) - float(before["score"]), 1),
        },
        "method": "deterministic",
    }


@router.get("/{clause_id}/precedents")
def clause_precedents(
    clause_id: str, limit: int = Query(default=3, ge=1, le=10)
) -> Dict[str, Any]:
    """Feature 4 — Precedent Recall: closest approved wording, with similarity."""
    with session_scope() as session:
        clause = session.get(Clause, clause_id)
        if clause is None:
            raise HTTPException(status_code=404, detail="Clause not found")
        text, category = clause.text, clause.category

    precedents = recall_precedents(text, category, limit=limit)
    return {
        "clause_id": clause_id,
        "category": category,
        "count": len(precedents),
        "precedents": precedents,
        "note": (
            "Similarity is cosine distance in the active embedding space. Demo mode "
            "uses local hashed embeddings, which score lower than the OpenAI "
            "embeddings used when an API key is configured."
        ),
    }


@router.get("/{clause_id}/similar")
def clause_similar(
    clause_id: str, limit: int = Query(default=5, ge=1, le=20)
) -> Dict[str, Any]:
    """Similar clauses from other contracts — Qdrant retrieval role 2."""
    with session_scope() as session:
        clause = session.get(Clause, clause_id)
        if clause is None:
            raise HTTPException(status_code=404, detail="Clause not found")
        text, category, contract_id = clause.text, clause.category, clause.contract_id

    similar = find_similar_clauses(
        text, category, exclude_contract_id=contract_id, limit=limit
    )
    return {
        "clause_id": clause_id,
        "category": category,
        "count": len(similar),
        "similar_clauses": similar,
    }
