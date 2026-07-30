"""
Immutable audit trail.

Every AI decision and human action is appended here with a timestamp, an actor,
and a SHA-256 hash chained to its predecessor:

    hash_n = sha256(seq ‖ timestamp ‖ actor ‖ event ‖ object ‖ payload ‖ hash_n-1)

"Immutable" is a real claim, so it is enforced rather than asserted: there is no
update or delete path, and `verify_chain()` recomputes every hash and confirms
each entry points at its predecessor. Editing, reordering or removing any past
row breaks verification from that point on, which the Audit Log page surfaces.
The Audit Agent additionally narrates each entry into plain English.

Writes never raise into the caller. An audit failure must not roll back the
business action it is recording — a lost log line is bad, a lost contract review
is worse — so failures are logged and reported via `last_error`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select

from app.db import AuditEvent, session_scope, utcnow
from app.domain import ActorType

logger = logging.getLogger(__name__)

GENESIS_HASH = "0" * 64

_write_lock = threading.Lock()
last_error: Optional[str] = None


def _canonical_payload(payload: Optional[Dict[str, Any]]) -> str:
    """Deterministic JSON so the same content always hashes identically."""
    try:
        return json.dumps(payload or {}, sort_keys=True, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        return json.dumps({"unserialisable": str(payload)[:500]})


def compute_hash(
    *,
    seq: int,
    ts_iso: str,
    actor_type: str,
    actor_id: str,
    event_type: str,
    object_type: str,
    object_id: str,
    summary: str,
    payload: Optional[Dict[str, Any]],
    prev_hash: str,
) -> str:
    material = "‖".join(
        [
            str(seq),
            ts_iso,
            actor_type,
            actor_id,
            event_type,
            object_type,
            object_id,
            summary,
            _canonical_payload(payload),
            prev_hash,
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def record(
    *,
    event_type: str,
    object_type: str = "",
    object_id: str = "",
    contract_id: str = "",
    actor_type: str = ActorType.SYSTEM.value,
    actor_id: str = "system",
    actor_role: str = "",
    summary: str = "",
    compliance_note: str = "",
    payload: Optional[Dict[str, Any]] = None,
    narrate: bool = False,
) -> Optional[Dict[str, Any]]:
    """Append one audit entry. Returns the stored entry, or None on failure.

    `narrate=True` routes the event through the Audit Agent for a plain-English
    summary. Off by default because it costs an LLM call; used for the decisions
    a human will actually read.
    """
    global last_error

    if narrate and not summary:
        try:
            from app.agents import get_agent

            narration = get_agent("audit").narrate(
                {
                    "event_type": event_type,
                    "actor": actor_id,
                    "actor_role": actor_role,
                    "object_type": object_type,
                    "object_id": object_id,
                    **(payload or {}),
                }
            )
            summary = str(narration.get("summary") or "")
            compliance_note = compliance_note or str(narration.get("compliance_note") or "")
        except Exception as exc:
            logger.warning("Audit narration failed (%s); storing factual summary.", exc)

    if not summary:
        summary = f"{actor_id} performed {event_type} on {object_type} {object_id}".strip()

    try:
        # Serialised: the chain requires a strict order and each entry must read
        # the true current tail before hashing onto it.
        with _write_lock:
            with session_scope() as session:
                tail = session.execute(
                    select(AuditEvent).order_by(AuditEvent.seq.desc()).limit(1)
                ).scalar_one_or_none()
                prev_hash = tail.hash if tail else GENESIS_HASH
                next_seq = (tail.seq + 1) if tail else 1

                timestamp = utcnow()
                ts_iso = timestamp.astimezone(timezone.utc).isoformat()
                digest = compute_hash(
                    seq=next_seq,
                    ts_iso=ts_iso,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    event_type=event_type,
                    object_type=object_type,
                    object_id=object_id,
                    summary=summary,
                    payload=payload,
                    prev_hash=prev_hash,
                )

                entry = AuditEvent(
                    id=str(uuid.uuid4()),
                    seq=next_seq,
                    timestamp=timestamp,
                    ts_iso=ts_iso,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    actor_role=actor_role,
                    event_type=event_type,
                    object_type=object_type,
                    object_id=object_id,
                    contract_id=contract_id,
                    summary=summary,
                    compliance_note=compliance_note,
                    payload=payload or {},
                    prev_hash=prev_hash,
                    hash=digest,
                )
                session.add(entry)
                session.flush()
                last_error = None
                return _to_dict(entry)
    except Exception as exc:
        # Never propagate: the business action must survive an audit outage.
        last_error = f"{type(exc).__name__}: {exc}"
        logger.error("Audit write failed for %s: %s", event_type, last_error)
        return None


def _to_dict(entry: AuditEvent) -> Dict[str, Any]:
    return {
        "id": entry.id,
        "seq": entry.seq,
        "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
        "actor_type": entry.actor_type,
        "actor_id": entry.actor_id,
        "actor_role": entry.actor_role,
        "event_type": entry.event_type,
        "object_type": entry.object_type,
        "object_id": entry.object_id,
        "contract_id": entry.contract_id,
        "summary": entry.summary,
        "compliance_note": entry.compliance_note,
        "payload": entry.payload or {},
        "prev_hash": entry.prev_hash,
        "hash": entry.hash,
    }


def list_events(
    *,
    limit: int = 100,
    offset: int = 0,
    contract_id: Optional[str] = None,
    actor_type: Optional[str] = None,
    event_type: Optional[str] = None,
) -> Dict[str, Any]:
    with session_scope() as session:
        stmt = select(AuditEvent)
        count_stmt = select(func.count()).select_from(AuditEvent)

        if contract_id:
            stmt = stmt.where(AuditEvent.contract_id == contract_id)
            count_stmt = count_stmt.where(AuditEvent.contract_id == contract_id)
        if actor_type:
            stmt = stmt.where(AuditEvent.actor_type == actor_type)
            count_stmt = count_stmt.where(AuditEvent.actor_type == actor_type)
        if event_type:
            stmt = stmt.where(AuditEvent.event_type == event_type)
            count_stmt = count_stmt.where(AuditEvent.event_type == event_type)

        total = int(session.execute(count_stmt).scalar() or 0)
        rows = (
            session.execute(
                stmt.order_by(AuditEvent.seq.desc()).limit(limit).offset(offset)
            )
            .scalars()
            .all()
        )
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "events": [_to_dict(r) for r in rows],
        }


def verify_chain() -> Dict[str, Any]:
    """Recompute every hash and confirm the chain links. Proves tamper-evidence."""
    with session_scope() as session:
        rows = (
            session.execute(select(AuditEvent).order_by(AuditEvent.seq.asc()))
            .scalars()
            .all()
        )

    problems: List[Dict[str, Any]] = []
    expected_prev = GENESIS_HASH

    for row in rows:
        recomputed = compute_hash(
            seq=row.seq,
            ts_iso=row.ts_iso,
            actor_type=row.actor_type,
            actor_id=row.actor_id,
            event_type=row.event_type,
            object_type=row.object_type,
            object_id=row.object_id,
            summary=row.summary,
            payload=row.payload,
            prev_hash=row.prev_hash,
        )
        if recomputed != row.hash:
            problems.append(
                {
                    "seq": row.seq,
                    "issue": "content_hash_mismatch",
                    "detail": (
                        "Stored hash does not match recomputed content hash — this "
                        "entry was modified after it was written."
                    ),
                    "stored_hash": row.hash,
                    "recomputed_hash": recomputed,
                }
            )
        if row.prev_hash != expected_prev:
            problems.append(
                {
                    "seq": row.seq,
                    "issue": "broken_chain_link",
                    "detail": (
                        "prev_hash does not match the preceding entry's hash — an "
                        "entry was inserted, removed or reordered."
                    ),
                    "expected_prev_hash": expected_prev,
                    "stored_prev_hash": row.prev_hash,
                }
            )
        expected_prev = row.hash

    return {
        "valid": not problems,
        "entries_checked": len(rows),
        "problems": problems,
        "head_hash": rows[-1].hash if rows else GENESIS_HASH,
        "algorithm": "SHA-256 chained over (seq, timestamp, actor, event, object, payload, prev_hash)",
        "verified_at": utcnow().isoformat(),
    }


def stats() -> Dict[str, Any]:
    with session_scope() as session:
        total = int(session.execute(select(func.count()).select_from(AuditEvent)).scalar() or 0)
        by_actor = dict(
            session.execute(
                select(AuditEvent.actor_type, func.count()).group_by(AuditEvent.actor_type)
            ).all()
        )
        by_event = dict(
            session.execute(
                select(AuditEvent.event_type, func.count())
                .group_by(AuditEvent.event_type)
                .order_by(func.count().desc())
                .limit(12)
            ).all()
        )
    return {
        "total_events": total,
        "by_actor_type": {str(k): int(v) for k, v in by_actor.items()},
        "by_event_type": {str(k): int(v) for k, v in by_event.items()},
        "last_error": last_error,
    }
