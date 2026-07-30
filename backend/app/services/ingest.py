"""
The ingest and review pipeline — steps 1 through 5 of the core flow.

    upload → extract text → guardrail screen → split into clauses
           → persist + embed into Qdrant → classify → playbook → risk
           → redline → escalate → roll up contract risk → audit

Two entry points:

  * `ingest_document()` — synchronous and fast (no LLM calls). Returns as soon as
    the document is parsed, screened, split and indexed, so the UI can navigate
    straight to the contract while review runs separately.
  * `review_contract()` — a generator of progress events, so the same code drives
    both a blocking call and an SSE stream with per-clause progress.

Guardrails run *before* any agent sees the text: a contract is untrusted input,
and a counterparty can plant instructions inside a PDF.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Iterator, List, Optional

from sqlalchemy import delete, select

from app.agents import get_agent, run_clause_review_pipeline
from app.db import Clause, ClauseVersion, Contract, session_scope, utcnow
from app.domain import ActorType, ContractStatus, RiskLevel
from app.services import audit
from app.services.clauses import split_into_clauses
from app.services.extract import ExtractionError, extract_document
from app.services.guardrails import (
    evaluate_approval_gate,
    screen_agent_output,
    screen_document,
)
from app.services.qdrant_store import (
    find_similar_clauses,
    index_clauses,
    recall_precedents,
    retrieve_playbook_rules,
)
from app.services.seed import get_active_rules

logger = logging.getLogger(__name__)


class IngestError(Exception):
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — upload, extract, screen, split, embed
# ─────────────────────────────────────────────────────────────────────────────


def ingest_document(
    data: bytes,
    filename: str,
    *,
    uploaded_by: str = "unknown",
    actor_role: str = "",
    title: Optional[str] = None,
    counterparty: str = "",
    parse_metadata: bool = True,
) -> Dict[str, Any]:
    try:
        extracted = extract_document(data, filename)
    except ExtractionError as exc:
        raise IngestError(str(exc)) from exc

    if not extracted.text.strip():
        raise IngestError(
            "No text could be extracted. If this is a scanned document it needs OCR "
            "first — Dharma AI does not perform OCR."
        )

    # Guardrails before agents. A blocked document is still stored so a human can
    # inspect why, but it is not reviewed.
    screening = screen_document(extracted.text, source=f"upload:{filename}")
    safe_text = screening["safe_text"]

    clause_objs = split_into_clauses(safe_text)
    if not clause_objs:
        raise IngestError("Document parsed but no clauses could be identified.")

    contract_id = str(uuid.uuid4())
    resolved_title = (title or extracted.metadata.get("title") or filename or "Untitled").strip()

    parsed_metadata: Dict[str, Any] = {}
    if parse_metadata:
        try:
            parsed_metadata = get_agent("contract_parsing").parse(safe_text, filename)
        except Exception as exc:
            logger.warning("Contract parsing agent failed: %s", exc)
            parsed_metadata = {"error": str(exc)}

    status = (
        ContractStatus.FAILED.value
        if screening["blocked"]
        else ContractStatus.READY.value
    )

    with session_scope() as session:
        session.add(
            Contract(
                id=contract_id,
                title=resolved_title,
                filename=filename,
                status=status,
                uploaded_by=uploaded_by,
                counterparty=counterparty
                or _first_party(parsed_metadata.get("parties"), resolved_title),
                page_count=extracted.page_count,
                char_count=extracted.char_count,
                clause_count=len(clause_objs),
                extracted_text=safe_text,
                doc_metadata={
                    **extracted.to_dict(),
                    "original_filename": filename,
                    "size_bytes": len(data),
                },
                parsed_metadata=parsed_metadata,
                guardrail_report=screening,
                risk_score=0.0,
                risk_level=RiskLevel.LOW.value,
            )
        )
        # Flush so the contract row exists before anything references it.
        # SQLAlchemy's flush ordering across mappers is not guaranteed to satisfy
        # raw ForeignKey columns when no `relationship()` is declared, and Postgres
        # enforces the constraint immediately — this raised a ForeignKeyViolation.
        # Still one transaction, so the whole ingest remains atomic.
        session.flush()

        clause_rows: List[Dict[str, Any]] = []
        original_versions: List[Dict[str, Any]] = []
        for clause in clause_objs:
            clause_id = str(uuid.uuid4())
            session.add(
                Clause(
                    id=clause_id,
                    contract_id=contract_id,
                    index=clause.index,
                    label=clause.label,
                    heading=clause.heading or clause.display_title,
                    text=clause.text,
                    category="Other",
                    confidence=0.0,
                    approval_state="pending_human_approval",
                    current_version=1,
                )
            )
            # Version 1 is the original wording, so rollback always has a floor.
            # Collected and inserted after the clauses are flushed, for the same
            # foreign-key ordering reason as above.
            original_versions.append({"clause_id": clause_id, "text": clause.text})
            clause_rows.append(
                {
                    "id": clause_id,
                    "index": clause.index,
                    "heading": clause.heading or clause.display_title,
                    "text": clause.text,
                    "category": "Other",
                }
            )

        # Clauses now exist; their original versions can safely reference them.
        session.flush()
        for version in original_versions:
            session.add(
                ClauseVersion(
                    id=str(uuid.uuid4()),
                    clause_id=version["clause_id"],
                    contract_id=contract_id,
                    version_no=1,
                    text=version["text"],
                    source="original",
                    author=uploaded_by,
                    author_role=actor_role,
                    reason="Original clause text as extracted from the uploaded document.",
                )
            )

    # Index for semantic search immediately; categories are refined after review.
    try:
        index_clauses(contract_id, resolved_title, clause_rows)
    except Exception as exc:
        logger.warning("Qdrant clause indexing failed: %s", exc)

    audit.record(
        event_type="contract.uploaded",
        object_type="contract",
        object_id=contract_id,
        contract_id=contract_id,
        actor_type=ActorType.HUMAN.value,
        actor_id=uploaded_by,
        actor_role=actor_role,
        summary=(
            f"{uploaded_by} uploaded '{resolved_title}' ({len(clause_objs)} clauses, "
            f"{extracted.char_count} chars). Guardrail screening: "
            f"{screening['summary']}"
        ),
        payload={
            "filename": filename,
            "clause_count": len(clause_objs),
            "char_count": extracted.char_count,
            "guardrails_triggered": screening["requires_review"],
            "blocked": screening["blocked"],
            "sanitized_spans": screening["sanitized_spans"],
        },
    )

    return {
        "contract_id": contract_id,
        "title": resolved_title,
        "status": status,
        "clause_count": len(clause_objs),
        "page_count": extracted.page_count,
        "char_count": extracted.char_count,
        "extraction": extracted.to_dict(),
        "parsed_metadata": parsed_metadata,
        "guardrails": screening,
        "blocked": screening["blocked"],
        "clauses": clause_rows,
    }


def _first_party(parties: Any, fallback: str) -> str:
    if isinstance(parties, list) and parties:
        return str(parties[-1])[:200]
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Steps 2–5 — classify, validate, score, redline, escalate
# ─────────────────────────────────────────────────────────────────────────────


def review_contract(
    contract_id: str,
    *,
    actor_id: str = "system",
    actor_role: str = "",
    include_redline: bool = True,
    limit: Optional[int] = None,
) -> Iterator[Dict[str, Any]]:
    """Run the agent pipeline over every clause, yielding progress events.

    Event types: `start`, `clause_started`, `clause_done`, `contract_done`, `error`.
    """
    with session_scope() as session:
        contract = session.get(Contract, contract_id)
        if contract is None:
            yield {"type": "error", "error": f"Contract {contract_id} not found."}
            return
        contract_title = contract.title
        contract.status = ContractStatus.CLASSIFYING.value

        clause_query = (
            select(Clause).where(Clause.contract_id == contract_id).order_by(Clause.index)
        )
        if limit:
            clause_query = clause_query.limit(limit)
        clauses = session.execute(clause_query).scalars().all()
        clause_payloads = [
            {"id": c.id, "index": c.index, "heading": c.heading, "text": c.text}
            for c in clauses
        ]

    if not clause_payloads:
        yield {"type": "error", "error": "Contract has no clauses to review."}
        return

    yield {
        "type": "start",
        "contract_id": contract_id,
        "title": contract_title,
        "clause_count": len(clause_payloads),
    }

    # Full rule set for deterministic evaluation; Qdrant then narrows per clause
    # to the semantically relevant subset that goes into the prompt.
    all_rules = get_active_rules()
    scored: List[Dict[str, Any]] = []

    for payload in clause_payloads:
        yield {
            "type": "clause_started",
            "clause_id": payload["id"],
            "index": payload["index"],
            "heading": payload["heading"],
        }

        try:
            retrieved_rules = retrieve_playbook_rules(payload["text"], limit=6)
        except Exception as exc:
            logger.warning("Playbook retrieval failed: %s", exc)
            retrieved_rules = all_rules[:6]

        # Union of semantic hits and every deterministically-checkable rule: a
        # monetary threshold must fire on arithmetic even if the clause does not
        # read as semantically similar to the rule's description.
        rule_ids = {str(r.get("id")) for r in retrieved_rules}
        merged_rules = list(retrieved_rules) + [
            r for r in all_rules if str(r.get("id")) not in rule_ids
        ]

        try:
            similar = find_similar_clauses(
                payload["text"], "Other", exclude_contract_id=contract_id, limit=3
            )
        except Exception:
            similar = []

        try:
            result = run_clause_review_pipeline(
                payload["text"],
                heading=payload["heading"],
                clause_id=payload["id"],
                playbook_rules=merged_rules,
                similar_clauses=similar,
                include_redline=include_redline,
                include_escalation=True,
            )
        except Exception as exc:
            logger.exception("Clause review failed for %s", payload["id"])
            yield {
                "type": "error",
                "clause_id": payload["id"],
                "error": f"{type(exc).__name__}: {exc}",
            }
            continue

        data = result.to_dict()
        category = data.get("category") or "Other"

        # Precedent Recall now that the category is known.
        try:
            precedents = recall_precedents(payload["text"], category, limit=3)
        except Exception:
            precedents = []

        # Output guardrails on the agent results a human will act on.
        guardrails: Dict[str, Any] = {
            "risk": screen_agent_output(
                data.get("risk") or {},
                source_text=payload["text"],
                agent_name="Risk Assessment Agent",
            ),
            "classification": screen_agent_output(
                data.get("classification") or {},
                source_text=payload["text"],
                agent_name="Clause Classification Agent",
            ),
        }
        if data.get("redline"):
            guardrails["redline"] = screen_agent_output(
                data["redline"],
                source_text=payload["text"],
                agent_name="Redline Agent",
            )
            gate = evaluate_approval_gate(
                redline=data["redline"],
                risk_level=str(data.get("risk_level") or RiskLevel.LOW.value),
            )
            guardrails["approval_gate"] = gate.to_dict()

        with session_scope() as session:
            clause = session.get(Clause, payload["id"])
            if clause is not None:
                clause.category = category
                clause.confidence = float(data.get("confidence") or 0.0)
                clause.risk_score = float(data.get("risk_score") or 0.0)
                clause.risk_level = str(data.get("risk_level") or RiskLevel.LOW.value)
                clause.explanation = str(data.get("explanation") or "")
                clause.suggested_fix = str(data.get("suggested_fix") or "")
                clause.classification = data.get("classification") or {}
                clause.playbook = data.get("playbook") or {}
                clause.risk = data.get("risk") or {}
                clause.redline = {**(data.get("redline") or {}), "precedents": precedents}
                clause.escalation = data.get("escalation") or {}
                clause.guardrails = guardrails
                clause.agent_trace = data.get("agent_trace") or []

                # A proposed redline is a new version, held behind the approval gate.
                redline = data.get("redline") or {}
                suggested = str(redline.get("suggested") or "").strip()
                if suggested and suggested != clause.text.strip():
                    next_version = clause.current_version + 1
                    session.add(
                        ClauseVersion(
                            id=str(uuid.uuid4()),
                            clause_id=clause.id,
                            contract_id=contract_id,
                            version_no=next_version,
                            text=suggested,
                            source="ai_redline",
                            author="Redline Agent",
                            author_role="AI_AGENT",
                            reason=str(redline.get("reason") or "")[:2000],
                            risk_score=clause.risk_score,
                            risk_level=clause.risk_level,
                        )
                    )
                    clause.current_version = next_version

        scored.append(
            {
                "clause_id": payload["id"],
                "category": category,
                "score": float(data.get("risk_score") or 0.0),
                "level": str(data.get("risk_level") or RiskLevel.LOW.value),
            }
        )

        audit.record(
            event_type="clause.reviewed",
            object_type="clause",
            object_id=payload["id"],
            contract_id=contract_id,
            actor_type=ActorType.AI_AGENT.value,
            actor_id="Dharma AI clause review pipeline",
            summary=(
                f"Clause {payload['index'] + 1} ('{payload['heading'][:60]}') classified "
                f"as {category} (confidence {data.get('confidence')}), scored "
                f"{data.get('risk_score')}/100 ({data.get('risk_level')})."
            ),
            payload={
                "category": category,
                "confidence": data.get("confidence"),
                "risk_score": data.get("risk_score"),
                "risk_level": data.get("risk_level"),
                "playbook_violations": [
                    v.get("rule_id") for v in (data.get("playbook") or {}).get("violations", [])
                ],
                "escalated": (data.get("escalation") or {}).get("should_escalate"),
                "agent_trace": data.get("agent_trace"),
                "guardrails_flagged": [
                    k for k, v in guardrails.items()
                    if isinstance(v, dict) and v.get("requires_approval")
                ],
            },
        )

        yield {
            "type": "clause_done",
            "clause_id": payload["id"],
            "index": payload["index"],
            "heading": payload["heading"],
            "category": category,
            "confidence": data.get("confidence"),
            "risk_score": data.get("risk_score"),
            "risk_level": data.get("risk_level"),
            "explanation": data.get("explanation"),
            "escalated": (data.get("escalation") or {}).get("should_escalate"),
            "precedent_count": len(precedents),
            "progress": {
                "done": len(scored),
                "total": len(clause_payloads),
                "pct": round(100 * len(scored) / len(clause_payloads), 1),
            },
        }

    # Contract-level rollup.
    from app.agents.contract_agents import RiskAssessmentAgent

    rollup = RiskAssessmentAgent.rollup(scored)

    escalation_count = 0
    with session_scope() as session:
        contract = session.get(Contract, contract_id)
        if contract is not None:
            contract.risk_score = float(rollup["score"])
            contract.risk_level = str(rollup["level"])
            contract.risk_summary = rollup
            contract.status = ContractStatus.READY.value

        # Re-index with the resolved categories and risk levels so category- and
        # risk-filtered vector search is accurate.
        refreshed = (
            session.execute(
                select(Clause).where(Clause.contract_id == contract_id).order_by(Clause.index)
            )
            .scalars()
            .all()
        )
        reindex_payload = [
            {
                "id": c.id,
                "index": c.index,
                "heading": c.heading,
                "text": c.text,
                "category": c.category,
                "risk_level": c.risk_level,
                "risk_score": c.risk_score,
            }
            for c in refreshed
        ]
        escalation_count = sum(
            1 for c in refreshed if (c.escalation or {}).get("should_escalate")
        )

    try:
        index_clauses(contract_id, contract_title, reindex_payload)
    except Exception as exc:
        logger.warning("Qdrant re-index failed: %s", exc)

    # Populate the human review queue from the escalation decisions.
    created_tasks = create_review_tasks(contract_id)

    audit.record(
        event_type="contract.reviewed",
        object_type="contract",
        object_id=contract_id,
        contract_id=contract_id,
        actor_type=ActorType.AI_AGENT.value,
        actor_id="Dharma AI review pipeline",
        summary=(
            f"Review complete for '{contract_title}': {len(scored)} clauses, contract "
            f"risk {rollup['score']}/100 ({rollup['level']}), {escalation_count} clause(s) "
            f"escalated to human review."
        ),
        payload={"rollup": rollup, "review_tasks_created": created_tasks},
    )

    yield {
        "type": "contract_done",
        "contract_id": contract_id,
        "risk": rollup,
        "clauses_reviewed": len(scored),
        "escalated": escalation_count,
        "review_tasks_created": created_tasks,
    }


def create_review_tasks(contract_id: str) -> int:
    """Create reviewer-queue entries for clauses the Escalation Agent flagged."""
    from app.db import ReviewTask

    created = 0
    with session_scope() as session:
        clauses = (
            session.execute(select(Clause).where(Clause.contract_id == contract_id))
            .scalars()
            .all()
        )
        for clause in clauses:
            escalation = clause.escalation or {}
            if not escalation.get("should_escalate"):
                continue
            # Idempotent: re-running review must not duplicate open tasks.
            existing = session.execute(
                select(ReviewTask).where(
                    ReviewTask.clause_id == clause.id, ReviewTask.status == "open"
                )
            ).scalar_one_or_none()
            if existing is not None:
                continue

            session.add(
                ReviewTask(
                    id=str(uuid.uuid4()),
                    contract_id=contract_id,
                    clause_id=clause.id,
                    category=clause.category,
                    priority=str(escalation.get("priority") or "medium"),
                    reason=str(escalation.get("reason") or ""),
                    recommended_action=str(escalation.get("recommended_action") or ""),
                    assigned_role=str(escalation.get("assigned_role") or "REVIEWER"),
                    risk_score=clause.risk_score,
                    risk_level=clause.risk_level,
                    sla_hours=escalation.get("sla_hours"),
                    status="open",
                )
            )
            created += 1
    return created


def review_contract_blocking(contract_id: str, **kwargs: Any) -> Dict[str, Any]:
    """Drain `review_contract` and return the final summary."""
    events = list(review_contract(contract_id, **kwargs))
    final = next((e for e in reversed(events) if e["type"] == "contract_done"), None)
    errors = [e for e in events if e["type"] == "error"]
    return {
        "contract_id": contract_id,
        "completed": final is not None,
        "summary": final,
        "errors": errors,
        "events": events,
    }


def ingest_sample_contract(uploaded_by: str = "demo") -> Dict[str, Any]:
    """Load the bundled sample MSA. Backs the 'Load sample contract' button."""
    from app.services.seed import SAMPLE_CONTRACT_TEXT

    return ingest_document(
        SAMPLE_CONTRACT_TEXT.encode("utf-8"),
        "Acme-Vendor-Master-Services-Agreement.txt",
        uploaded_by=uploaded_by,
        title="Acme ⇄ Vendor Industries — Master Services Agreement",
        counterparty="Vendor Industries Ltd",
    )
