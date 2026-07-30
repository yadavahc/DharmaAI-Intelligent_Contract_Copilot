"""Playbook Manager — admin-defined rules, stored in Postgres and indexed in Qdrant."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.db import PlaybookRule, session_scope
from app.domain import ActorType, ClauseCategory
from app.schemas import PlaybookRuleIn, PlaybookRuleUpdate
from app.services import audit
from app.services.qdrant_store import PLAYBOOK, get_store, index_playbook_rules
from app.services.seed import _rule_to_dict, seed_playbook

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/playbook", tags=["playbook"])

VALID_RULE_TYPES = {
    "monetary_threshold",
    "duration_threshold",
    "forbidden_language",
    "required_language",
}
VALID_OPERATORS = {"", "gt", "gte", "lt", "lte", "eq"}


def _require_admin(actor_role: str) -> None:
    if actor_role != "ADMIN":
        raise HTTPException(
            status_code=403,
            detail=f"Role '{actor_role}' may not modify the playbook. Requires ADMIN.",
        )


def _validate(rule: Dict[str, Any]) -> None:
    rule_type = rule.get("rule_type")
    if rule_type not in VALID_RULE_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"rule_type must be one of {sorted(VALID_RULE_TYPES)}",
        )
    if rule.get("operator") not in VALID_OPERATORS:
        raise HTTPException(
            status_code=422, detail=f"operator must be one of {sorted(VALID_OPERATORS)}"
        )

    category = rule.get("category")
    if category not in ("*", "Any") and category not in ClauseCategory.values():
        raise HTTPException(
            status_code=422,
            detail=f"category must be '*' or one of {ClauseCategory.values()}",
        )

    if rule_type in ("monetary_threshold", "duration_threshold"):
        if rule.get("threshold") is None:
            raise HTTPException(
                status_code=422, detail=f"{rule_type} requires a numeric threshold"
            )
        if not rule.get("operator"):
            raise HTTPException(
                status_code=422, detail=f"{rule_type} requires a comparison operator"
            )
    if rule_type in ("forbidden_language", "required_language") and not rule.get("keywords"):
        raise HTTPException(
            status_code=422, detail=f"{rule_type} requires at least one keyword"
        )
    # A wildcard required-language rule would fire on every unrelated clause and
    # inflate the whole contract's score — see heuristics.evaluate_playbook_rules.
    if rule_type == "required_language" and category in ("*", "Any"):
        raise HTTPException(
            status_code=422,
            detail=(
                "A required_language rule must target a specific clause category. "
                "Applied globally it would fire on every clause that is not about "
                "its subject."
            ),
        )


@router.get("")
def list_rules(
    category: Optional[str] = None,
    active_only: bool = Query(default=False),
) -> Dict[str, Any]:
    with session_scope() as session:
        stmt = select(PlaybookRule)
        if category:
            stmt = stmt.where(PlaybookRule.category == category)
        if active_only:
            stmt = stmt.where(PlaybookRule.active.is_(True))
        rows = session.execute(stmt.order_by(PlaybookRule.id)).scalars().all()
        rules = [_rule_to_dict(r) for r in rows]

    return {
        "count": len(rules),
        "rules": rules,
        "rule_types": sorted(VALID_RULE_TYPES),
        "operators": sorted(o for o in VALID_OPERATORS if o),
        "categories": ["*"] + ClauseCategory.values(),
        "vector_indexed": get_store().count(PLAYBOOK),
    }


@router.post("")
def create_rule(
    body: PlaybookRuleIn,
    actor_id: str = Query(default="system"),
    actor_role: str = Query(default="ADMIN"),
) -> Dict[str, Any]:
    _require_admin(actor_role)
    payload = body.model_dump()
    _validate(payload)

    rule_id = (payload.get("id") or "").strip() or _generate_rule_id(payload)

    with session_scope() as session:
        if session.get(PlaybookRule, rule_id) is not None:
            raise HTTPException(status_code=409, detail=f"Rule '{rule_id}' already exists")
        session.add(
            PlaybookRule(
                id=rule_id,
                title=payload["title"],
                category=payload["category"],
                rule_type=payload["rule_type"],
                operator=payload.get("operator") or "",
                threshold=payload.get("threshold"),
                keywords=payload.get("keywords") or [],
                severity=payload.get("severity") or "Medium",
                risk_points=int(payload.get("risk_points") or 20),
                guidance=payload.get("guidance") or "",
                preferred_language=payload.get("preferred_language") or "",
                active=bool(payload.get("active", True)),
                created_by=actor_id,
            )
        )

    _reindex()
    audit.record(
        event_type="playbook.rule_created",
        object_type="playbook_rule",
        object_id=rule_id,
        actor_type=ActorType.HUMAN.value,
        actor_id=actor_id,
        actor_role=actor_role,
        summary=f"{actor_id} created playbook rule '{rule_id}': {payload['title']}",
        payload=payload,
    )
    return {"created": True, "id": rule_id, **payload}


def _generate_rule_id(payload: Dict[str, Any]) -> str:
    category = str(payload.get("category") or "GEN")
    prefix = re.sub(r"[^A-Z]", "", category.upper())[:5] or "GEN"
    with session_scope() as session:
        existing = {
            r.id
            for r in session.execute(
                select(PlaybookRule).where(PlaybookRule.id.like(f"PB-{prefix}-%"))
            )
            .scalars()
            .all()
        }
    for n in range(1, 1000):
        candidate = f"PB-{prefix}-{n:03d}"
        if candidate not in existing:
            return candidate
    raise HTTPException(status_code=500, detail="Could not allocate a rule id")


@router.patch("/{rule_id}")
def update_rule(
    rule_id: str,
    body: PlaybookRuleUpdate,
    actor_id: str = Query(default="system"),
    actor_role: str = Query(default="ADMIN"),
) -> Dict[str, Any]:
    _require_admin(actor_role)
    changes = {k: v for k, v in body.model_dump().items() if v is not None}
    if not changes:
        raise HTTPException(status_code=422, detail="No fields to update")

    with session_scope() as session:
        rule = session.get(PlaybookRule, rule_id)
        if rule is None:
            raise HTTPException(status_code=404, detail="Rule not found")

        before = _rule_to_dict(rule)
        merged = {**before, **changes}
        _validate(merged)

        for key, value in changes.items():
            setattr(rule, key, value)
        after = _rule_to_dict(rule)

    _reindex()
    audit.record(
        event_type="playbook.rule_updated",
        object_type="playbook_rule",
        object_id=rule_id,
        actor_type=ActorType.HUMAN.value,
        actor_id=actor_id,
        actor_role=actor_role,
        summary=f"{actor_id} updated playbook rule '{rule_id}' ({', '.join(changes)}).",
        payload={"before": before, "after": after, "changed_fields": list(changes)},
    )
    return {"updated": True, **after}


@router.delete("/{rule_id}")
def delete_rule(
    rule_id: str,
    actor_id: str = Query(default="system"),
    actor_role: str = Query(default="ADMIN"),
) -> Dict[str, Any]:
    _require_admin(actor_role)
    with session_scope() as session:
        rule = session.get(PlaybookRule, rule_id)
        if rule is None:
            raise HTTPException(status_code=404, detail="Rule not found")
        snapshot = _rule_to_dict(rule)
        session.delete(rule)

    try:
        get_store().delete_by_filter(PLAYBOOK, {"id": rule_id})
    except Exception as exc:
        logger.warning("Vector delete failed for rule %s: %s", rule_id, exc)
    _reindex()

    audit.record(
        event_type="playbook.rule_deleted",
        object_type="playbook_rule",
        object_id=rule_id,
        actor_type=ActorType.HUMAN.value,
        actor_id=actor_id,
        actor_role=actor_role,
        summary=f"{actor_id} deleted playbook rule '{rule_id}'.",
        payload=snapshot,
    )
    return {"deleted": True, "id": rule_id}


@router.post("/reseed")
def reseed(
    actor_id: str = Query(default="system"), actor_role: str = Query(default="ADMIN")
) -> Dict[str, Any]:
    _require_admin(actor_role)
    result = seed_playbook(force=True)
    audit.record(
        event_type="playbook.reseeded",
        object_type="playbook",
        actor_type=ActorType.HUMAN.value,
        actor_id=actor_id,
        actor_role=actor_role,
        summary=f"{actor_id} reseeded the default playbook.",
        payload=result,
    )
    return result


@router.post("/test")
def test_rules(
    clause_text: str = Query(..., max_length=20000),
    category: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    """Dry-run the playbook against arbitrary text — the 'Test rule' affordance."""
    from app.agents.heuristics import classify_clause_heuristic, evaluate_playbook_rules
    from app.services.seed import get_active_rules

    resolved = category or classify_clause_heuristic(clause_text).category
    rules = get_active_rules()
    findings = evaluate_playbook_rules(clause_text, resolved, rules)

    return {
        "category": resolved,
        "rules_evaluated": len(rules),
        "violations": [f.to_dict() for f in findings],
        "compliant": not findings,
        "total_risk_points": sum(f.points for f in findings),
    }


def _reindex() -> None:
    """Re-embed all active rules so semantic retrieval reflects the change."""
    from app.services.seed import get_active_rules

    try:
        index_playbook_rules(get_active_rules())
    except Exception as exc:
        logger.warning("Playbook re-index failed: %s", exc)
