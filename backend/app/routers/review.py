"""
Human reviewer queue and the approval gate.

This is where guardrail #4 is actually enforced. `apply_gate` in
`services/guardrails.py` is the only path to a finalised redline, and it rejects
unauthorised roles and invalid state transitions by raising — so the gate is a
real control, not a UI affordance.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app.db import Clause, ClauseVersion, Contract, ReviewTask, session_scope, utcnow
from app.domain import ActorType, ReviewDecision
from app.schemas import ReviewDecisionIn
from app.services import audit
from app.services.guardrails import (
    GATE_APPROVED,
    GATE_EDITED,
    GATE_FINALIZED,
    GATE_PENDING,
    GATE_REJECTED,
    ApprovalGateError,
    apply_gate,
)
from app.services.qdrant_store import index_precedent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/review", tags=["review"])

_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


@router.get("/queue")
def review_queue(
    status: str = Query(default="open"),
    priority: Optional[str] = None,
    contract_id: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=300),
) -> Dict[str, Any]:
    """The escalation queue, highest priority and risk first."""
    with session_scope() as session:
        stmt = select(ReviewTask)
        if status and status != "all":
            stmt = stmt.where(ReviewTask.status == status)
        if priority:
            stmt = stmt.where(ReviewTask.priority == priority)
        if contract_id:
            stmt = stmt.where(ReviewTask.contract_id == contract_id)

        tasks = session.execute(stmt.limit(limit)).scalars().all()

        enriched: List[Dict[str, Any]] = []
        for task in tasks:
            clause = session.get(Clause, task.clause_id)
            contract = session.get(Contract, task.contract_id)
            enriched.append(
                {
                    "id": task.id,
                    "contract_id": task.contract_id,
                    "contract_title": contract.title if contract else "",
                    "clause_id": task.clause_id,
                    "clause_heading": clause.heading if clause else "",
                    "clause_text": clause.text if clause else "",
                    "category": task.category,
                    "priority": task.priority,
                    "reason": task.reason,
                    "recommended_action": task.recommended_action,
                    "assigned_role": task.assigned_role,
                    "risk_score": task.risk_score,
                    "risk_level": task.risk_level,
                    "sla_hours": task.sla_hours,
                    "status": task.status,
                    "decision": task.decision,
                    "decision_note": task.decision_note,
                    "decided_by": task.decided_by,
                    "decided_at": task.decided_at.isoformat() if task.decided_at else None,
                    "approval_state": clause.approval_state if clause else None,
                    "redline": (clause.redline or {}) if clause else {},
                    "created_at": task.created_at.isoformat() if task.created_at else None,
                }
            )

        counts = {
            str(s): int(c)
            for s, c in session.execute(
                select(ReviewTask.status, func.count()).group_by(ReviewTask.status)
            ).all()
        }

    enriched.sort(
        key=lambda t: (
            _PRIORITY_ORDER.get(str(t["priority"]), 3),
            -float(t["risk_score"] or 0),
        )
    )
    return {"count": len(enriched), "counts_by_status": counts, "tasks": enriched}


@router.get("/queue/{task_id}")
def get_task(task_id: str) -> Dict[str, Any]:
    with session_scope() as session:
        task = session.get(ReviewTask, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Review task not found")
        clause = session.get(Clause, task.clause_id)
        contract = session.get(Contract, task.contract_id)
        versions = (
            session.execute(
                select(ClauseVersion)
                .where(ClauseVersion.clause_id == task.clause_id)
                .order_by(ClauseVersion.version_no)
            )
            .scalars()
            .all()
        )
        return {
            "id": task.id,
            "status": task.status,
            "priority": task.priority,
            "reason": task.reason,
            "recommended_action": task.recommended_action,
            "risk_score": task.risk_score,
            "risk_level": task.risk_level,
            "contract": {
                "id": task.contract_id,
                "title": contract.title if contract else "",
            },
            "clause": {
                "id": task.clause_id,
                "heading": clause.heading if clause else "",
                "text": clause.text if clause else "",
                "category": clause.category if clause else "",
                "explanation": clause.explanation if clause else "",
                "suggested_fix": clause.suggested_fix if clause else "",
                "redline": (clause.redline or {}) if clause else {},
                "guardrails": (clause.guardrails or {}) if clause else {},
                "approval_state": clause.approval_state if clause else None,
            },
            "versions": [
                {
                    "version_no": v.version_no,
                    "text": v.text,
                    "source": v.source,
                    "author": v.author,
                    "reason": v.reason,
                    "created_at": v.created_at.isoformat() if v.created_at else None,
                }
                for v in versions
            ],
        }


@router.post("/queue/{task_id}/decide")
def decide(task_id: str, body: ReviewDecisionIn) -> Dict[str, Any]:
    """Record a human decision through the approval gate.

    `approve` / `edit` finalise the redline and, being human-accepted language,
    add it to the precedent library that Precedent Recall searches. `comment`
    records a note and deliberately leaves the gate shut.
    """
    with session_scope() as session:
        task = session.get(ReviewTask, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Review task not found")
        clause = session.get(Clause, task.clause_id)
        if clause is None:
            raise HTTPException(status_code=404, detail="Clause not found")
        contract = session.get(Contract, task.contract_id)

        current_state = clause.approval_state or GATE_PENDING
        clause_heading = clause.heading
        clause_category = clause.category
        contract_title = contract.title if contract else ""
        contract_id = task.contract_id
        clause_id = task.clause_id
        redline = dict(clause.redline or {})

    try:
        gate = apply_gate(
            current_state=current_state,
            decision=body.decision,
            actor_role=body.actor_role,
            actor_id=body.actor_id,
            edited_text=body.edited_text,
        )
    except ApprovalGateError as exc:
        # 403 for authorisation, 409 for an invalid state transition.
        code = 403 if "may not approve" in str(exc) else 409
        raise HTTPException(status_code=code, detail=str(exc)) from exc

    new_state = gate["state"]
    final_text: Optional[str] = None

    with session_scope() as session:
        clause = session.get(Clause, clause_id)
        task = session.get(ReviewTask, task_id)
        if clause is None or task is None:
            raise HTTPException(status_code=404, detail="Review task no longer exists")

        if new_state == GATE_APPROVED:
            # Approving adopts the AI-suggested language, if any.
            suggested = str(redline.get("suggested") or "").strip()
            final_text = suggested or clause.text
        elif new_state == GATE_EDITED:
            final_text = str(body.edited_text or "").strip()

        if final_text and final_text != clause.text.strip():
            next_version = clause.current_version + 1
            session.add(
                ClauseVersion(
                    id=str(uuid.uuid4()),
                    clause_id=clause.id,
                    contract_id=clause.contract_id,
                    version_no=next_version,
                    text=final_text,
                    source="human_edit" if new_state == GATE_EDITED else "ai_redline",
                    author=body.actor_id,
                    author_role=body.actor_role,
                    reason=body.note
                    or (
                        "Reviewer edited and approved the clause."
                        if new_state == GATE_EDITED
                        else "Reviewer approved the AI-suggested redline."
                    ),
                    risk_score=clause.risk_score,
                    risk_level=clause.risk_level,
                )
            )
            clause.current_version = next_version
            clause.text = final_text

        # Finalise only when the gate allows it.
        clause.approval_state = (
            GATE_FINALIZED if gate["finalizable"] else new_state
        )

        task.status = "open" if body.decision == "comment" else "closed"
        task.decision = body.decision
        task.decision_note = body.note
        task.edited_text = body.edited_text or ""
        task.decided_by = body.actor_id
        task.decided_by_role = body.actor_role
        task.decided_at = utcnow() if body.decision != "comment" else None
        approval_state = clause.approval_state

    # Human-approved wording becomes precedent for future contracts.
    if gate["finalizable"] and final_text:
        try:
            index_precedent(
                final_text,
                clause_category,
                contract_title=contract_title,
                contract_id=contract_id,
                clause_id=clause_id,
                approved_by=body.actor_id,
                risk_level="Approved",
                notes=body.note or f"Approved by {body.actor_id} via review queue.",
            )
        except Exception as exc:
            logger.warning("Precedent indexing failed: %s", exc)

    audit.record(
        event_type=f"review.{body.decision}",
        object_type="clause",
        object_id=clause_id,
        contract_id=contract_id,
        actor_type=ActorType.HUMAN.value,
        actor_id=body.actor_id,
        actor_role=body.actor_role,
        summary=(
            f"{body.actor_id} ({body.actor_role}) recorded decision '{body.decision}' on "
            f"clause '{clause_heading}' of '{contract_title}'. Approval gate: "
            f"{current_state} → {approval_state}."
        ),
        compliance_note=(
            "Human approval gate satisfied; redline finalised."
            if gate["finalizable"]
            else "Gate remains closed; no redline finalised."
        ),
        payload={
            "decision": body.decision,
            "note": body.note,
            "previous_state": current_state,
            "new_state": approval_state,
            "finalized": gate["finalizable"],
            "added_to_precedent_library": bool(gate["finalizable"] and final_text),
        },
        narrate=True,
    )

    return {
        "task_id": task_id,
        "clause_id": clause_id,
        "decision": body.decision,
        "previous_state": current_state,
        "approval_state": approval_state,
        "finalized": gate["finalizable"],
        "text": final_text,
    }


@router.get("/gate/{clause_id}")
def gate_status(clause_id: str) -> Dict[str, Any]:
    """Current approval-gate state for a clause — drives the UI's gate badge."""
    with session_scope() as session:
        clause = session.get(Clause, clause_id)
        if clause is None:
            raise HTTPException(status_code=404, detail="Clause not found")
        state = clause.approval_state or GATE_PENDING
        gate_report = (clause.guardrails or {}).get("approval_gate", {})

    return {
        "clause_id": clause_id,
        "state": state,
        "finalized": state == GATE_FINALIZED,
        "blocks_finalisation": state == GATE_PENDING,
        "allowed_transitions": (
            [GATE_APPROVED, GATE_REJECTED, GATE_EDITED] if state == GATE_PENDING else []
        ),
        "authorized_roles": ["REVIEWER", "ADMIN"],
        "gate_report": gate_report,
    }
