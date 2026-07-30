"""Contract endpoints: upload, list, detail, streamed review, executive summary."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.db import Clause, Contract, Negotiation, ReviewTask, session_scope
from app.domain import ActorType, ClauseCategory, RiskLevel
from app.services import audit
from app.services.extract import SUPPORTED_EXTENSIONS
from app.services.ingest import (
    IngestError,
    ingest_document,
    ingest_sample_contract,
    review_contract,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/contracts", tags=["contracts"])


def _sse(event: Dict[str, Any]) -> str:
    """Server-sent-events frame."""
    return f"data: {json.dumps(event, default=str)}\n\n"


SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    # Nginx and similar proxies buffer by default, which would defeat streaming.
    "X-Accel-Buffering": "no",
}


@router.post("/upload")
async def upload_contract(
    file: UploadFile = File(...),
    title: Optional[str] = Form(default=None),
    counterparty: str = Form(default=""),
    actor_id: str = Form(default="anonymous"),
    actor_role: str = Form(default="BUSINESS_USER"),
) -> Dict[str, Any]:
    """Upload a PDF/DOCX/TXT contract: extract, screen, split, embed."""
    data = await file.read()
    try:
        return ingest_document(
            data,
            file.filename or "upload",
            uploaded_by=actor_id,
            actor_role=actor_role,
            title=title,
            counterparty=counterparty,
        )
    except IngestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Upload failed")
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}") from exc


@router.post("/sample")
def upload_sample(actor_id: str = Query(default="demo@dharma.ai")) -> Dict[str, Any]:
    """Ingest the bundled sample MSA — the one-click demo path."""
    try:
        return ingest_sample_contract(actor_id)
    except IngestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/supported-types")
def supported_types() -> Dict[str, Any]:
    return {"extensions": sorted(SUPPORTED_EXTENSIONS), "max_mb": 25}


@router.get("")
def list_contracts(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: Optional[str] = None,
    risk_level: Optional[str] = None,
) -> Dict[str, Any]:
    with session_scope() as session:
        stmt = select(Contract)
        count_stmt = select(func.count()).select_from(Contract)
        if status:
            stmt = stmt.where(Contract.status == status)
            count_stmt = count_stmt.where(Contract.status == status)
        if risk_level:
            stmt = stmt.where(Contract.risk_level == risk_level)
            count_stmt = count_stmt.where(Contract.risk_level == risk_level)

        total = int(session.execute(count_stmt).scalar() or 0)
        rows = (
            session.execute(
                stmt.order_by(Contract.created_at.desc()).limit(limit).offset(offset)
            )
            .scalars()
            .all()
        )
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "contracts": [_contract_summary(c) for c in rows],
        }


def _contract_summary(c: Contract) -> Dict[str, Any]:
    return {
        "id": c.id,
        "title": c.title,
        "filename": c.filename,
        "status": c.status,
        "counterparty": c.counterparty,
        "uploaded_by": c.uploaded_by,
        "clause_count": c.clause_count,
        "page_count": c.page_count,
        "char_count": c.char_count,
        "risk_score": c.risk_score,
        "risk_level": c.risk_level,
        "risk_summary": c.risk_summary or {},
        "has_executive_summary": bool(c.executive_summary),
        "guardrails_flagged": bool((c.guardrail_report or {}).get("requires_review")),
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


@router.get("/dashboard")
def dashboard() -> Dict[str, Any]:
    """Aggregates for the dashboard charts and KPI counters."""
    with session_scope() as session:
        contract_count = int(session.execute(select(func.count()).select_from(Contract)).scalar() or 0)
        clause_count = int(session.execute(select(func.count()).select_from(Clause)).scalar() or 0)

        risk_distribution = {level.value: 0 for level in RiskLevel}
        for level, count in session.execute(
            select(Clause.risk_level, func.count()).group_by(Clause.risk_level)
        ).all():
            if level in risk_distribution:
                risk_distribution[str(level)] = int(count)

        category_distribution = {
            str(cat): int(count)
            for cat, count in session.execute(
                select(Clause.category, func.count())
                .group_by(Clause.category)
                .order_by(func.count().desc())
            ).all()
        }

        negotiation_status = {
            str(outcome): int(count)
            for outcome, count in session.execute(
                select(Negotiation.outcome, func.count()).group_by(Negotiation.outcome)
            ).all()
        }

        open_reviews = int(
            session.execute(
                select(func.count()).select_from(ReviewTask).where(ReviewTask.status == "open")
            ).scalar()
            or 0
        )
        review_by_priority = {
            str(p): int(c)
            for p, c in session.execute(
                select(ReviewTask.priority, func.count())
                .where(ReviewTask.status == "open")
                .group_by(ReviewTask.priority)
            ).all()
        }

        avg_confidence = float(
            session.execute(
                select(func.avg(Clause.confidence)).where(Clause.confidence > 0)
            ).scalar()
            or 0.0
        )
        avg_contract_risk = float(
            session.execute(
                select(func.avg(Contract.risk_score)).where(Contract.risk_score > 0)
            ).scalar()
            or 0.0
        )

        # Confidence histogram for the AI-confidence chart.
        confidence_buckets = {"0-50%": 0, "50-70%": 0, "70-85%": 0, "85-100%": 0}
        for (confidence,) in session.execute(
            select(Clause.confidence).where(Clause.confidence > 0)
        ).all():
            value = float(confidence or 0) * 100
            if value < 50:
                confidence_buckets["0-50%"] += 1
            elif value < 70:
                confidence_buckets["50-70%"] += 1
            elif value < 85:
                confidence_buckets["70-85%"] += 1
            else:
                confidence_buckets["85-100%"] += 1

        recent_contracts = [
            _contract_summary(c)
            for c in session.execute(
                select(Contract).order_by(Contract.created_at.desc()).limit(5)
            )
            .scalars()
            .all()
        ]

        top_risk_clauses = [
            {
                "id": c.id,
                "contract_id": c.contract_id,
                "heading": c.heading,
                "category": c.category,
                "risk_score": c.risk_score,
                "risk_level": c.risk_level,
                "explanation": (c.explanation or "")[:220],
            }
            for c in session.execute(
                select(Clause).order_by(Clause.risk_score.desc()).limit(6)
            )
            .scalars()
            .all()
        ]

    recent_activity = audit.list_events(limit=12)["events"]

    return {
        "kpis": {
            "contracts": contract_count,
            "clauses": clause_count,
            "open_reviews": open_reviews,
            "avg_confidence": round(avg_confidence, 3),
            "avg_contract_risk": round(avg_contract_risk, 1),
            "high_risk_clauses": risk_distribution.get(RiskLevel.HIGH.value, 0)
            + risk_distribution.get(RiskLevel.CRITICAL.value, 0),
        },
        "risk_distribution": risk_distribution,
        "category_distribution": category_distribution,
        "negotiation_status": negotiation_status,
        "review_by_priority": review_by_priority,
        "confidence_buckets": confidence_buckets,
        "recent_contracts": recent_contracts,
        "top_risk_clauses": top_risk_clauses,
        "recent_activity": recent_activity,
        "agent_telemetry": _telemetry_summary(),
    }


def _telemetry_summary() -> Dict[str, Any]:
    from app.agents.model import recorder

    return recorder.summary()


@router.get("/{contract_id}")
def get_contract(contract_id: str, include_text: bool = Query(default=False)) -> Dict[str, Any]:
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
        payload = _contract_summary(contract)
        payload.update(
            {
                "parsed_metadata": contract.parsed_metadata or {},
                "doc_metadata": contract.doc_metadata or {},
                "guardrail_report": contract.guardrail_report or {},
                "executive_summary": contract.executive_summary or {},
                "clauses": [_clause_summary(c) for c in clauses],
            }
        )
        if include_text:
            payload["extracted_text"] = contract.extracted_text
        return payload


def _clause_summary(c: Clause) -> Dict[str, Any]:
    return {
        "id": c.id,
        "contract_id": c.contract_id,
        "index": c.index,
        "label": c.label,
        "heading": c.heading,
        "text": c.text,
        "category": c.category,
        "confidence": c.confidence,
        "risk_score": c.risk_score,
        "risk_level": c.risk_level,
        "explanation": c.explanation,
        "suggested_fix": c.suggested_fix,
        "redline": c.redline or {},
        "playbook": c.playbook or {},
        "escalation": c.escalation or {},
        "guardrails": c.guardrails or {},
        "agent_trace": c.agent_trace or [],
        "approval_state": c.approval_state,
        "current_version": c.current_version,
    }


@router.post("/{contract_id}/review/stream")
def review_stream(
    contract_id: str,
    actor_id: str = Query(default="system"),
    actor_role: str = Query(default=""),
    include_redline: bool = Query(default=True),
) -> StreamingResponse:
    """Run the review pipeline, streaming per-clause progress over SSE."""

    def generate():
        try:
            for event in review_contract(
                contract_id,
                actor_id=actor_id,
                actor_role=actor_role,
                include_redline=include_redline,
            ):
                yield _sse(event)
        except Exception as exc:
            logger.exception("Review stream failed")
            yield _sse({"type": "error", "error": f"{type(exc).__name__}: {exc}"})
        yield _sse({"type": "stream_end"})

    return StreamingResponse(
        generate(), media_type="text/event-stream", headers=SSE_HEADERS
    )


@router.post("/{contract_id}/review")
def review_blocking(
    contract_id: str,
    actor_id: str = Query(default="system"),
    include_redline: bool = Query(default=True),
) -> Dict[str, Any]:
    """Blocking review — used by the e2e test and by clients without SSE."""
    from app.services.ingest import review_contract_blocking

    result = review_contract_blocking(
        contract_id, actor_id=actor_id, include_redline=include_redline
    )
    if not result["completed"] and result["errors"]:
        raise HTTPException(status_code=400, detail=result["errors"][0].get("error"))
    return result["summary"] or {"contract_id": contract_id, "completed": False}


@router.post("/{contract_id}/executive-summary")
def executive_summary(
    contract_id: str,
    refresh: bool = Query(default=False),
    actor_id: str = Query(default="system"),
) -> Dict[str, Any]:
    """Feature 5 — the one-page plain-English executive brief."""
    from app.agents import get_agent

    with session_scope() as session:
        contract = session.get(Contract, contract_id)
        if contract is None:
            raise HTTPException(status_code=404, detail="Contract not found")
        if contract.executive_summary and not refresh:
            return {"contract_id": contract_id, "cached": True, **contract.executive_summary}

        clauses = (
            session.execute(
                select(Clause).where(Clause.contract_id == contract_id).order_by(Clause.index)
            )
            .scalars()
            .all()
        )
        title = contract.title
        risk_summary = contract.risk_summary or {}
        clause_payload = [
            {
                "heading": c.heading,
                "category": c.category,
                "risk_level": c.risk_level,
                "risk_score": c.risk_score,
                "explanation": c.explanation,
                "text": c.text,
            }
            for c in clauses
        ]

    if not clause_payload:
        raise HTTPException(
            status_code=400, detail="Contract has no reviewed clauses to summarise."
        )

    summary = get_agent("executive_summary").summarize(title, clause_payload, risk_summary)

    with session_scope() as session:
        contract = session.get(Contract, contract_id)
        if contract is not None:
            contract.executive_summary = summary

    audit.record(
        event_type="contract.executive_summary_generated",
        object_type="contract",
        object_id=contract_id,
        contract_id=contract_id,
        actor_type=ActorType.AI_AGENT.value,
        actor_id="Executive AI Summary Agent",
        summary=f"Executive brief generated for '{title}'.",
        payload={"overall_recommendation": summary.get("overall_recommendation")},
    )
    return {"contract_id": contract_id, "cached": False, **summary}


@router.delete("/{contract_id}")
def delete_contract(
    contract_id: str, actor_id: str = Query(default="system"), actor_role: str = Query(default="")
) -> Dict[str, Any]:
    if actor_role not in ("ADMIN",):
        raise HTTPException(
            status_code=403, detail="Only an ADMIN may delete a contract."
        )

    from app.services.qdrant_store import CLAUSES, get_store

    with session_scope() as session:
        contract = session.get(Contract, contract_id)
        if contract is None:
            raise HTTPException(status_code=404, detail="Contract not found")
        title = contract.title
        session.delete(contract)
        # Clauses/versions cascade via FK; review tasks are keyed by id only.
        for task in (
            session.execute(select(ReviewTask).where(ReviewTask.contract_id == contract_id))
            .scalars()
            .all()
        ):
            session.delete(task)

    try:
        get_store().delete_by_filter(CLAUSES, {"contract_id": contract_id})
    except Exception as exc:
        logger.warning("Vector cleanup failed for %s: %s", contract_id, exc)

    audit.record(
        event_type="contract.deleted",
        object_type="contract",
        object_id=contract_id,
        contract_id=contract_id,
        actor_type=ActorType.HUMAN.value,
        actor_id=actor_id,
        actor_role=actor_role,
        summary=f"{actor_id} deleted contract '{title}'.",
    )
    return {"deleted": True, "contract_id": contract_id}
