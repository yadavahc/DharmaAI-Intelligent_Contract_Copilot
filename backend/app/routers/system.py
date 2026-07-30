"""System, agent-introspection, and demo-control endpoints.

`/api/agents/*` exists so a reviewer can confirm the Lyzr claim from the running
service rather than from the README: which runtime is live, which classes are
bound, every agent's role and persona, and the real per-call telemetry.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Query

from app.agents import agent_roster, runtime_info
from app.agents.model import recorder
from app.agents.pipeline import run_lyzr_linear_pipeline
from app.config import settings
from app.db import db_health
from app.services import audit
from app.services.qdrant_store import COLLECTION_PURPOSE, get_store

router = APIRouter(tags=["system"])


@router.get("/api/health")
def health() -> Dict[str, Any]:
    store = get_store()
    return {
        "status": "ok",
        "demo_mode": settings.demo_mode,
        "openai_key_present": bool(
            (settings.openai_api_key or "").strip()
            and not (settings.openai_api_key or "").startswith("sk-replace")
        ),
        "model": settings.openai_model,
        "database": db_health(),
        "vector_store": store.health(),
        "lyzr": runtime_info(),
        "thresholds": {
            "risk_high": settings.risk_high_threshold,
            "risk_medium": settings.risk_medium_threshold,
            "negotiation_max_rounds": settings.negotiation_max_rounds,
        },
    }


@router.get("/api/agents")
def list_agents() -> Dict[str, Any]:
    """Every agent, its Lyzr role, persona, task instructions and hand-offs."""
    return {
        "runtime": runtime_info(),
        "count": len(agent_roster()),
        "agents": agent_roster(),
    }


@router.get("/api/agents/runtime")
def agents_runtime() -> Dict[str, Any]:
    """Which Lyzr runtime served this request — genuine SDK or the shim."""
    return runtime_info()


@router.get("/api/agents/telemetry")
def agents_telemetry(limit: int = Query(default=40, ge=1, le=200)) -> Dict[str, Any]:
    """Recent LLM calls with agent attribution, latency and token counts."""
    return {"summary": recorder.summary(), "recent_calls": recorder.recent(limit)}


@router.post("/api/agents/pipeline/demo")
def pipeline_demo(
    clause_text: str = Query(
        default=(
            "12.1 Limitation of Liability. Supplier shall have unlimited liability "
            "for any breach of this Agreement, and Customer waives any right to a "
            "jury trial."
        ),
        max_length=6000,
    ),
    heading: str = Query(default="Limitation of Liability", max_length=300),
) -> Dict[str, Any]:
    """Run the four ingest agents as a native Lyzr `LinearSyncPipeline`.

    Returns each task with its agent role, `input_tasks` wiring and output, so the
    framework's own chaining is directly observable.
    """
    from app.services.seed import get_active_rules

    return run_lyzr_linear_pipeline(
        clause_text, heading=heading, playbook_rules=get_active_rules()
    )


@router.get("/api/vector/health")
def vector_health() -> Dict[str, Any]:
    return {
        "store": get_store().health(),
        "collection_purposes": COLLECTION_PURPOSE,
    }


@router.post("/api/demo/seed")
def demo_seed() -> Dict[str, Any]:
    """Idempotently (re)seed the playbook and precedent library."""
    from app.services.seed import seed_all

    return seed_all()


@router.post("/api/demo/reset")
def demo_reset(
    include_vectors: bool = Query(default=True),
    load_sample: bool = Query(default=False),
) -> Dict[str, Any]:
    """Wipe all data and reseed. Used by the e2e test and the demo reset button."""
    from app.db import reset_db
    from app.services.ingest import ingest_sample_contract
    from app.services.seed import seed_all

    reset_db()
    if include_vectors:
        get_store().clear()

    result: Dict[str, Any] = {"reset": True, "seed": seed_all()}

    if load_sample:
        ingested = ingest_sample_contract("demo@dharma.ai")
        result["sample_contract_id"] = ingested["contract_id"]
        result["sample_clause_count"] = ingested["clause_count"]

    audit.record(
        event_type="system.reset",
        object_type="system",
        actor_id="system",
        summary="All contract data was reset and reference data reseeded.",
    )
    return result
