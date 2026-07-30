"""
Negotiation endpoints — the Live Agent Theater.

`/stream` is the centrepiece: it runs the two-agent loop and streams every event
(thinking → turn → risk → coach → outcome → escalation → done) over SSE so the UI
can render the exchange as it happens. Persistence and negotiation-memory
indexing happen as the stream completes, so a client that disconnects mid-way
still leaves a consistent record of the turns that did occur.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.agents import get_agent
from app.agents.pipeline import NegotiationOrchestrator
from app.config import settings
from app.db import (
    Clause,
    ClauseVersion,
    Contract,
    Negotiation,
    NegotiationTurn,
    session_scope,
    utcnow,
)
from app.domain import ActorType, NegotiationOutcome
from app.schemas import CoachRequest
from app.services import audit
from app.services.ingest import create_review_tasks
from app.services.qdrant_store import (
    index_negotiation_memory,
    recall_negotiation_memory,
    retrieve_playbook_rules,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/negotiations", tags=["negotiation"])

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _sse(event: Dict[str, Any]) -> str:
    return f"data: {json.dumps(event, default=str)}\n\n"


def _load_clause(clause_id: str) -> Dict[str, Any]:
    with session_scope() as session:
        clause = session.get(Clause, clause_id)
        if clause is None:
            raise HTTPException(status_code=404, detail="Clause not found")
        contract = session.get(Contract, clause.contract_id)
        return {
            "id": clause.id,
            "contract_id": clause.contract_id,
            "contract_title": contract.title if contract else "",
            "heading": clause.heading,
            "text": clause.text,
            "category": clause.category,
            "risk_score": clause.risk_score,
            "risk_level": clause.risk_level,
        }


def negotiation_events(
    *,
    clause_id: str,
    max_rounds: Optional[int] = None,
    include_coach: bool = True,
    actor_id: str = "system",
    actor_role: str = "",
) -> Any:
    """Run the negotiation and yield raw event dicts.

    Shared by the SSE endpoint and the blocking endpoint so both drive identical
    logic. Deliberately returns plain dicts rather than a `StreamingResponse`:
    Starlette wraps sync generators via `iterate_in_threadpool`, which makes
    `response.body_iterator` async and therefore not reusable from sync code.
    """
    clause = _load_clause(clause_id)
    negotiation_id = str(uuid.uuid4())
    rounds = max_rounds or settings.negotiation_max_rounds

    try:
        rules = retrieve_playbook_rules(clause["text"], clause["category"], limit=5)
    except Exception:
        rules = []
    try:
        memory = recall_negotiation_memory(clause["text"], clause["category"], limit=3)
    except Exception:
        memory = []

    with session_scope() as session:
        session.add(
            Negotiation(
                id=negotiation_id,
                contract_id=clause["contract_id"],
                clause_id=clause_id,
                category=clause["category"],
                outcome=NegotiationOutcome.PENDING.value,
                max_rounds=rounds,
                initial_risk=float(clause["risk_score"] or 0.0),
            )
        )

    audit.record(
        event_type="negotiation.started",
        object_type="negotiation",
        object_id=negotiation_id,
        contract_id=clause["contract_id"],
        actor_type=ActorType.HUMAN.value,
        actor_id=actor_id,
        actor_role=actor_role,
        summary=(
            f"{actor_id} started a {rounds}-round agent negotiation on clause "
            f"'{clause['heading']}' ({clause['category']}, risk {clause['risk_score']})."
        ),
        payload={
            "clause_id": clause_id,
            "max_rounds": rounds,
            "memory_hits": len(memory),
            "playbook_rules": [r.get("id") for r in rules],
        },
    )

    orchestrator = NegotiationOrchestrator(
        clause["text"],
        clause["category"],
        initial_risk=float(clause["risk_score"] or 0.0),
        max_rounds=rounds,
        playbook_rules=rules,
        memory=memory,
        include_coach=include_coach,
    )

    yield {
        "type": "meta",
        "negotiation_id": negotiation_id,
        "clause_id": clause_id,
        "clause_heading": clause["heading"],
        "contract_id": clause["contract_id"],
        "contract_title": clause["contract_title"],
        "category": clause["category"],
        "memory_hits": len(memory),
        "playbook_rule_ids": [r.get("id") for r in rules],
    }

    pending_coach: Dict[int, Dict[str, Any]] = {}
    turn_rows: List[Dict[str, Any]] = []
    final: Dict[str, Any] = {}

    try:
        for event in orchestrator.stream():
            if event["type"] == "turn":
                turn_rows.append(dict(event))
            elif event["type"] == "coach":
                pending_coach[int(event.get("round") or 0)] = dict(event)
            elif event["type"] in ("done", "error"):
                final = dict(event)
            yield event
    except Exception as exc:
        logger.exception("Negotiation failed")
        yield {"type": "error", "error": f"{type(exc).__name__}: {exc}"}

    # Persist whatever actually happened, even on a partial run.
    try:
        _persist_negotiation(
            negotiation_id=negotiation_id,
            clause=clause,
            orchestrator=orchestrator,
            turn_rows=turn_rows,
            coaching=pending_coach,
            final=final,
            actor_id=actor_id,
            actor_role=actor_role,
        )
        yield {"type": "persisted", "negotiation_id": negotiation_id}
    except Exception as exc:
        logger.exception("Negotiation persistence failed")
        yield {"type": "error", "error": f"persistence failed: {exc}"}

    yield {"type": "stream_end", "negotiation_id": negotiation_id}


@router.post("/stream")
def negotiate_stream(
    clause_id: str = Query(...),
    max_rounds: Optional[int] = Query(default=None, ge=1, le=10),
    include_coach: bool = Query(default=True),
    actor_id: str = Query(default="system"),
    actor_role: str = Query(default=""),
) -> StreamingResponse:
    """Run Organization vs Counterparty, streaming the exchange live over SSE."""

    def generate():
        for event in negotiation_events(
            clause_id=clause_id,
            max_rounds=max_rounds,
            include_coach=include_coach,
            actor_id=actor_id,
            actor_role=actor_role,
        ):
            yield _sse(event)

    return StreamingResponse(
        generate(), media_type="text/event-stream", headers=SSE_HEADERS
    )


def _persist_negotiation(
    *,
    negotiation_id: str,
    clause: Dict[str, Any],
    orchestrator: NegotiationOrchestrator,
    turn_rows: List[Dict[str, Any]],
    coaching: Dict[int, Dict[str, Any]],
    final: Dict[str, Any],
    actor_id: str,
    actor_role: str,
) -> None:
    outcome = orchestrator.outcome
    final_risk = float(final.get("final_risk_score") or orchestrator.current_risk or 0.0)
    final_language = str(final.get("final_language") or orchestrator.final_language or "")
    rounds_used = int(final.get("rounds_used") or (max((t["round"] for t in turn_rows), default=0)))
    escalated = bool(final.get("escalated"))

    with session_scope() as session:
        negotiation = session.get(Negotiation, negotiation_id)
        if negotiation is not None:
            negotiation.outcome = outcome
            negotiation.rounds_used = rounds_used
            negotiation.final_risk = final_risk
            negotiation.final_language = final_language
            negotiation.escalated = escalated
            negotiation.summary = final
            negotiation.completed_at = utcnow()

        for turn in turn_rows:
            round_no = int(turn.get("round") or 0)
            session.add(
                NegotiationTurn(
                    id=str(uuid.uuid4()),
                    negotiation_id=negotiation_id,
                    round=round_no,
                    side=str(turn.get("side") or ""),
                    agent_role=str(turn.get("agent_role") or ""),
                    message=str(turn.get("message") or ""),
                    stance=str(turn.get("stance") or ""),
                    proposed_language=str(turn.get("proposed_language") or ""),
                    concession=str(turn.get("concession") or ""),
                    rationale=str(turn.get("rationale") or ""),
                    projected_risk_score=float(turn.get("projected_risk_score") or 0.0),
                    confidence=float(turn.get("confidence") or 0.0),
                    coaching=(
                        coaching.get(round_no, {})
                        if str(turn.get("side")) == "organization"
                        else {}
                    ),
                )
            )

        # A negotiated position is a new clause version, still behind the gate.
        clause_row = session.get(Clause, clause["id"])
        if clause_row is not None and final_language.strip():
            if final_language.strip() != clause_row.text.strip():
                next_version = clause_row.current_version + 1
                session.add(
                    ClauseVersion(
                        id=str(uuid.uuid4()),
                        clause_id=clause_row.id,
                        contract_id=clause_row.contract_id,
                        version_no=next_version,
                        text=final_language,
                        source="negotiation",
                        author="Organization Agent",
                        author_role="AI_AGENT",
                        reason=(
                            f"Position reached after {rounds_used} negotiation round(s); "
                            f"outcome: {outcome}."
                        ),
                        risk_score=final_risk,
                    )
                )
                clause_row.current_version = next_version
            clause_row.risk_score = final_risk
            from app.domain import risk_level_for_score

            clause_row.risk_level = risk_level_for_score(
                final_risk, settings.risk_high_threshold, settings.risk_medium_threshold
            ).value
            if escalated:
                escalation = dict(clause_row.escalation or {})
                escalation.update(
                    {
                        "should_escalate": True,
                        "reason": (
                            escalation.get("reason") or ""
                        )
                        + f" Negotiation outcome: {outcome}.",
                        "priority": escalation.get("priority") or "high",
                        "negotiation_id": negotiation_id,
                    }
                )
                clause_row.escalation = escalation

    if escalated:
        create_review_tasks(clause["contract_id"])

    # Qdrant retrieval role 5 — remember this negotiation for future ones.
    try:
        index_negotiation_memory(
            negotiation_id=negotiation_id,
            clause_text=clause["text"],
            category=clause["category"],
            outcome=outcome,
            rounds_used=rounds_used,
            final_language=final_language,
            risk_before=float(clause["risk_score"] or 0.0),
            risk_after=final_risk,
            transcript_summary=" | ".join(
                f"{t.get('side')}: {str(t.get('message'))[:120]}" for t in turn_rows[-4:]
            ),
        )
    except Exception as exc:
        logger.warning("Negotiation memory indexing failed: %s", exc)

    audit.record(
        event_type="negotiation.completed",
        object_type="negotiation",
        object_id=negotiation_id,
        contract_id=clause["contract_id"],
        actor_type=ActorType.AI_AGENT.value,
        actor_id="Organization Agent ⇄ Counterparty Agent",
        summary=(
            f"Negotiation on '{clause['heading']}' ended '{outcome}' after "
            f"{rounds_used} round(s). Risk {clause['risk_score']} → {final_risk}. "
            f"{'Escalated to human review.' if escalated else 'No escalation required.'}"
        ),
        payload={
            "outcome": outcome,
            "rounds_used": rounds_used,
            "risk_before": clause["risk_score"],
            "risk_after": final_risk,
            "escalated": escalated,
            "turns": len(turn_rows),
        },
    )


@router.post("/run")
def negotiate_blocking(
    clause_id: str = Query(...),
    max_rounds: Optional[int] = Query(default=None, ge=1, le=10),
    include_coach: bool = Query(default=True),
    actor_id: str = Query(default="system"),
) -> Dict[str, Any]:
    """Blocking negotiation — used by the e2e test and non-SSE clients."""
    events: List[Dict[str, Any]] = list(
        negotiation_events(
            clause_id=clause_id,
            max_rounds=max_rounds,
            include_coach=include_coach,
            actor_id=actor_id,
            actor_role="",
        )
    )

    meta = next((e for e in events if e.get("type") == "meta"), {})
    done = next((e for e in events if e.get("type") in ("done", "error")), {})
    return {
        "negotiation_id": meta.get("negotiation_id"),
        "clause_id": clause_id,
        "outcome": done.get("outcome"),
        "summary": done,
        "turns": [e for e in events if e.get("type") == "turn"],
        "coaching": [e for e in events if e.get("type") == "coach"],
        "escalation": next((e for e in events if e.get("type") == "escalation"), {}),
    }


@router.get("")
def list_negotiations(
    limit: int = Query(default=50, ge=1, le=200),
    contract_id: Optional[str] = None,
    outcome: Optional[str] = None,
) -> Dict[str, Any]:
    with session_scope() as session:
        stmt = select(Negotiation)
        if contract_id:
            stmt = stmt.where(Negotiation.contract_id == contract_id)
        if outcome:
            stmt = stmt.where(Negotiation.outcome == outcome)
        rows = (
            session.execute(stmt.order_by(Negotiation.created_at.desc()).limit(limit))
            .scalars()
            .all()
        )
        return {
            "count": len(rows),
            "negotiations": [
                {
                    "id": n.id,
                    "contract_id": n.contract_id,
                    "clause_id": n.clause_id,
                    "category": n.category,
                    "outcome": n.outcome,
                    "rounds_used": n.rounds_used,
                    "max_rounds": n.max_rounds,
                    "initial_risk": n.initial_risk,
                    "final_risk": n.final_risk,
                    "risk_reduction": round((n.initial_risk or 0) - (n.final_risk or 0), 1),
                    "escalated": n.escalated,
                    "created_at": n.created_at.isoformat() if n.created_at else None,
                    "completed_at": n.completed_at.isoformat() if n.completed_at else None,
                }
                for n in rows
            ],
        }


@router.get("/{negotiation_id}")
def get_negotiation(negotiation_id: str) -> Dict[str, Any]:
    with session_scope() as session:
        negotiation = session.get(Negotiation, negotiation_id)
        if negotiation is None:
            raise HTTPException(status_code=404, detail="Negotiation not found")
        turns = (
            session.execute(
                select(NegotiationTurn)
                .where(NegotiationTurn.negotiation_id == negotiation_id)
                .order_by(NegotiationTurn.round, NegotiationTurn.created_at)
            )
            .scalars()
            .all()
        )
        clause = session.get(Clause, negotiation.clause_id)
        return {
            "id": negotiation.id,
            "contract_id": negotiation.contract_id,
            "clause_id": negotiation.clause_id,
            "clause_heading": clause.heading if clause else "",
            "clause_text": clause.text if clause else "",
            "category": negotiation.category,
            "outcome": negotiation.outcome,
            "rounds_used": negotiation.rounds_used,
            "max_rounds": negotiation.max_rounds,
            "initial_risk": negotiation.initial_risk,
            "final_risk": negotiation.final_risk,
            "final_language": negotiation.final_language,
            "escalated": negotiation.escalated,
            "summary": negotiation.summary or {},
            "turns": [
                {
                    "round": t.round,
                    "side": t.side,
                    "agent_role": t.agent_role,
                    "message": t.message,
                    "stance": t.stance,
                    "proposed_language": t.proposed_language,
                    "concession": t.concession,
                    "rationale": t.rationale,
                    "projected_risk_score": t.projected_risk_score,
                    "confidence": t.confidence,
                    "coaching": t.coaching or {},
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                }
                for t in turns
            ],
        }


@router.post("/coach")
def coach(body: CoachRequest) -> Dict[str, Any]:
    """Feature 3 — Strategy Coach on demand for the side panel."""
    try:
        memory = recall_negotiation_memory(body.clause_text, body.category, limit=3)
    except Exception:
        memory = []
    return get_agent("strategy_coach").coach(
        body.clause_text,
        body.category,
        round_no=body.round,
        history=body.history,
        proposed_redline=body.proposed_redline,
        current_risk=body.current_risk,
        memory=memory,
    )
