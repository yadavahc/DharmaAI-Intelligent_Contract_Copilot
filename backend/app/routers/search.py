"""Semantic search across all four Qdrant collections."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from app.schemas import SearchRequest
from app.services.qdrant_store import (
    CLAUSES,
    NEGOTIATIONS,
    PLAYBOOK,
    PRECEDENTS,
    COLLECTION_PURPOSE,
    get_store,
    search_clauses,
)

router = APIRouter(prefix="/api/search", tags=["search"])

_SCOPES = {
    "clauses": CLAUSES,
    "precedents": PRECEDENTS,
    "negotiations": NEGOTIATIONS,
    "playbook": PLAYBOOK,
}


@router.post("")
def search(body: SearchRequest) -> Dict[str, Any]:
    """Vector search, scoped to one collection.

    `clauses` supports category / contract / risk-level filters, which is what
    makes this useful rather than a toy: "show me every uncapped-liability clause
    rated High across all contracts" is a filter plus a vector query.
    """
    scope = body.scope if body.scope in _SCOPES else "clauses"

    if scope == "clauses":
        results = search_clauses(
            body.query,
            limit=body.limit,
            category=body.category,
            contract_id=body.contract_id,
            risk_level=body.risk_level,
        )
    else:
        filters: Dict[str, Any] = {}
        if body.category:
            filters["category"] = body.category
        hits = get_store().search(
            _SCOPES[scope], body.query, limit=body.limit, filters=filters or None
        )
        results = [h.to_dict() for h in hits]

    store = get_store()
    return {
        "query": body.query,
        "scope": scope,
        "collection": _SCOPES[scope],
        "collection_purpose": COLLECTION_PURPOSE[_SCOPES[scope]],
        "count": len(results),
        "results": results,
        "backend": store.backend,
        "filters_applied": {
            "category": body.category,
            "contract_id": body.contract_id,
            "risk_level": body.risk_level,
        },
    }


@router.get("/scopes")
def scopes() -> Dict[str, Any]:
    store = get_store()
    return {
        "scopes": [
            {
                "key": key,
                "collection": collection,
                "purpose": COLLECTION_PURPOSE[collection],
                "points": store.count(collection),
            }
            for key, collection in _SCOPES.items()
        ],
        "backend": store.backend,
    }
