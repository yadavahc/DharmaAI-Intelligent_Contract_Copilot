"""Audit log endpoints: listing, chain verification, statistics."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Query

from app.services import audit

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
def list_events(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    contract_id: Optional[str] = None,
    actor_type: Optional[str] = None,
    event_type: Optional[str] = None,
) -> Dict[str, Any]:
    return audit.list_events(
        limit=limit,
        offset=offset,
        contract_id=contract_id,
        actor_type=actor_type,
        event_type=event_type,
    )


@router.get("/verify")
def verify() -> Dict[str, Any]:
    """Recompute the whole hash chain and report any tampering.

    A `valid: false` result names the specific entry and whether its content was
    modified or an entry was inserted/removed/reordered.
    """
    return audit.verify_chain()


@router.get("/stats")
def stats() -> Dict[str, Any]:
    return audit.stats()
