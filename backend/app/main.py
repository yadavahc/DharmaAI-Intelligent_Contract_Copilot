"""
Dharma AI — FastAPI application entry point.

Startup is deliberately fault-tolerant: the database, the vector store and the
LLM each degrade independently (Postgres→SQLite, Qdrant→in-memory,
OpenAI→deterministic demo mode) so a missing dependency downgrades one capability
instead of taking down the demo. `GET /api/health` reports exactly which backend
is live for each.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.agents import runtime_info
from app.config import settings
from app.observability import capture_exception, init_error_monitoring
from app.routers import (
    audit as audit_router,
    clauses,
    contracts,
    guardrails,
    negotiation,
    playbook,
    review,
    search,
    system,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("dharma")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("─" * 68)
    logger.info("Dharma AI backend starting")

    monitoring = init_error_monitoring()
    logger.info("Error monitoring: %s", monitoring["sink"])

    runtime = runtime_info()
    logger.info(
        "Lyzr runtime: %s%s (genuine SDK: %s)",
        runtime["lyzr_runtime"],
        f" v{runtime['lyzr_version']}" if runtime.get("lyzr_version") else "",
        runtime["is_genuine_sdk"],
    )
    if not runtime["is_genuine_sdk"]:
        logger.warning(
            "lyzr-automata not importable (%s); using the signature-identical "
            "shim in agents/lyzr_compat.py. Install with: "
            "pip install --no-deps --ignore-requires-python -r requirements-lyzr.txt",
            runtime.get("import_error"),
        )

    from app.db import init_db

    logger.info("Database backend: %s", init_db())

    from app.services.qdrant_store import get_store

    store = get_store()
    store.connect()
    logger.info("Vector store backend: %s", store.backend)

    if settings.demo_mode:
        logger.warning(
            "DEMO MODE is active: agents return deterministic fixtures and "
            "embeddings are computed locally. No OpenAI calls will be made. "
            "Set a real OPENAI_API_KEY and DHARMA_DEMO_MODE=false for live agents."
        )
    else:
        logger.info("Live mode: OpenAI model %s", settings.openai_model)

    try:
        from app.services.seed import seed_all

        seeded = seed_all()
        logger.info(
            "Reference data ready: %s playbook rules, %s precedents.",
            seeded["playbook"].get("created") or seeded["playbook"].get("existing"),
            seeded["precedents"].get("created") or seeded["precedents"].get("existing"),
        )
    except Exception as exc:
        logger.error("Seeding failed (%s); the playbook may be empty.", exc)

    logger.info("Ready on http://%s:%s", settings.backend_host, settings.backend_port)
    logger.info("─" * 68)
    yield
    logger.info("Dharma AI backend shutting down")


app = FastAPI(
    title="Dharma AI",
    description=(
        "AI contract review and negotiation agent. Multi-agent orchestration via "
        "the Lyzr framework; retrieval via Qdrant across four distinct roles."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.backend_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a structured error instead of an opaque 500, and report it."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)

    # Routed to Sentry when a DSN is configured, otherwise to structured logs.
    # Secrets are scrubbed either way; see app/observability.py.
    capture_exception(
        exc,
        context={
            "method": request.method,
            "path": str(request.url.path),
            "query": dict(request.query_params),
            "actor": request.headers.get("X-Dharma-Actor"),
            "role": request.headers.get("X-Dharma-Role"),
        },
    )

    return JSONResponse(
        status_code=500,
        content={
            "detail": f"{type(exc).__name__}: {exc}",
            "path": str(request.url.path),
        },
    )


app.include_router(system.router)
app.include_router(contracts.router)
app.include_router(clauses.router)
app.include_router(negotiation.router)
app.include_router(playbook.router)
app.include_router(review.router)
app.include_router(audit_router.router)
app.include_router(search.router)
app.include_router(guardrails.router)


@app.get("/")
def root():
    return {
        "service": "Dharma AI",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/health",
        "agents": "/api/agents",
        "lyzr_runtime": runtime_info()["lyzr_runtime"],
        "demo_mode": settings.demo_mode,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=True,
    )
