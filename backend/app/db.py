"""
Persistence layer.

Schema ownership is split so that no table has two owners:

  * **Prisma** owns the auth tables (`User`, `Account`, `Session`,
    `VerificationToken`) because NextAuth's Prisma adapter requires that exact
    shape. Managed by `prisma migrate` from the frontend.
  * **SQLAlchemy** (this module) owns the domain tables — contracts, clauses,
    versions, negotiations, review queue, audit log, playbook rules — created via
    `init_db()` at backend startup.

Both point at the same Postgres database and never touch the same table, which
removes the drift risk that comes from mirroring one schema in two ORMs.

If Postgres is unreachable, the engine falls back to a local SQLite file so the
demo and the Playwright run still work end to end. Same models, same queries —
only the driver changes. `db_health()` reports which backend is live.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────────────────────────


class Contract(Base):
    __tablename__ = "dharma_contracts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(500), default="")
    filename: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(32), default="uploaded", index=True)
    uploaded_by: Mapped[str] = mapped_column(String(255), default="")
    counterparty: Mapped[str] = mapped_column(String(255), default="")

    page_count: Mapped[int] = mapped_column(Integer, default=0)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    clause_count: Mapped[int] = mapped_column(Integer, default=0)

    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    risk_level: Mapped[str] = mapped_column(String(16), default="Low")

    extracted_text: Mapped[str] = mapped_column(Text, default="")
    doc_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    parsed_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    risk_summary: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    guardrail_report: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    executive_summary: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Clause(Base):
    __tablename__ = "dharma_clauses"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    contract_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("dharma_contracts.id", ondelete="CASCADE"), index=True
    )
    index: Mapped[int] = mapped_column(Integer, default=0)
    label: Mapped[str] = mapped_column(String(64), default="")
    heading: Mapped[str] = mapped_column(String(500), default="")
    text: Mapped[str] = mapped_column(Text, default="")

    category: Mapped[str] = mapped_column(String(64), default="Other", index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)

    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    risk_level: Mapped[str] = mapped_column(String(16), default="Low", index=True)
    explanation: Mapped[str] = mapped_column(Text, default="")
    suggested_fix: Mapped[str] = mapped_column(Text, default="")

    # Full agent outputs, kept verbatim so the UI can show the reasoning trail.
    classification: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    playbook: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    risk: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    redline: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    escalation: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    guardrails: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    agent_trace: Mapped[Any] = mapped_column(JSON, default=list)

    # Human-approval gate state — see services/guardrails.py.
    approval_state: Mapped[str] = mapped_column(
        String(40), default="pending_human_approval", index=True
    )
    current_version: Mapped[int] = mapped_column(Integer, default=1)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ClauseVersion(Base):
    """Append-only clause history, enabling visual diffs and rollback."""

    __tablename__ = "dharma_clause_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    clause_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("dharma_clauses.id", ondelete="CASCADE"), index=True
    )
    contract_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    text: Mapped[str] = mapped_column(Text, default="")
    # "original" | "ai_redline" | "negotiation" | "human_edit" | "rollback"
    source: Mapped[str] = mapped_column(String(32), default="original")
    author: Mapped[str] = mapped_column(String(255), default="")
    author_role: Mapped[str] = mapped_column(String(32), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    risk_level: Mapped[str] = mapped_column(String(16), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Negotiation(Base):
    __tablename__ = "dharma_negotiations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    contract_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    clause_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    category: Mapped[str] = mapped_column(String(64), default="")
    outcome: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    rounds_used: Mapped[int] = mapped_column(Integer, default=0)
    max_rounds: Mapped[int] = mapped_column(Integer, default=4)
    initial_risk: Mapped[float] = mapped_column(Float, default=0.0)
    final_risk: Mapped[float] = mapped_column(Float, default=0.0)
    final_language: Mapped[str] = mapped_column(Text, default="")
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    summary: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class NegotiationTurn(Base):
    __tablename__ = "dharma_negotiation_turns"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    negotiation_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("dharma_negotiations.id", ondelete="CASCADE"), index=True
    )
    round: Mapped[int] = mapped_column(Integer, default=1)
    side: Mapped[str] = mapped_column(String(24), default="")
    agent_role: Mapped[str] = mapped_column(String(120), default="")
    message: Mapped[str] = mapped_column(Text, default="")
    stance: Mapped[str] = mapped_column(String(24), default="")
    proposed_language: Mapped[str] = mapped_column(Text, default="")
    concession: Mapped[str] = mapped_column(Text, default="")
    rationale: Mapped[str] = mapped_column(Text, default="")
    projected_risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    coaching: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReviewTask(Base):
    """Human reviewer queue entry produced by the Escalation Agent."""

    __tablename__ = "dharma_review_tasks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    contract_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    clause_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    negotiation_id: Mapped[str] = mapped_column(String(64), default="")
    category: Mapped[str] = mapped_column(String(64), default="")
    priority: Mapped[str] = mapped_column(String(16), default="medium", index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    recommended_action: Mapped[str] = mapped_column(Text, default="")
    assigned_role: Mapped[str] = mapped_column(String(32), default="REVIEWER")
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    risk_level: Mapped[str] = mapped_column(String(16), default="")
    sla_hours: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(String(24), default="open", index=True)
    decision: Mapped[str] = mapped_column(String(24), default="")
    decision_note: Mapped[str] = mapped_column(Text, default="")
    edited_text: Mapped[str] = mapped_column(Text, default="")
    decided_by: Mapped[str] = mapped_column(String(255), default="")
    decided_by_role: Mapped[str] = mapped_column(String(32), default="")
    decided_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    """Append-only, hash-chained record of every AI decision and human action."""

    __tablename__ = "dharma_audit_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, autoincrement=True, index=True, unique=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    # The exact timestamp string that went into the hash. Stored separately
    # because `DateTime(timezone=True)` does not round-trip identically across
    # backends — SQLite drops tzinfo and can truncate microseconds — which would
    # make a genuinely untampered chain fail verification. Hashing this literal
    # makes the chain verifiable on any backend.
    ts_iso: Mapped[str] = mapped_column(String(40), default="")

    actor_type: Mapped[str] = mapped_column(String(24), default="system", index=True)
    actor_id: Mapped[str] = mapped_column(String(255), default="")
    actor_role: Mapped[str] = mapped_column(String(64), default="")

    event_type: Mapped[str] = mapped_column(String(64), default="", index=True)
    object_type: Mapped[str] = mapped_column(String(48), default="")
    object_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    contract_id: Mapped[str] = mapped_column(String(64), default="", index=True)

    summary: Mapped[str] = mapped_column(Text, default="")
    compliance_note: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    # Tamper-evidence: hash covers this entry's content plus prev_hash.
    prev_hash: Mapped[str] = mapped_column(String(64), default="")
    hash: Mapped[str] = mapped_column(String(64), default="", index=True)


class PlaybookRule(Base):
    __tablename__ = "dharma_playbook_rules"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(300), default="")
    category: Mapped[str] = mapped_column(String(64), default="*", index=True)
    rule_type: Mapped[str] = mapped_column(String(48), default="forbidden_language")
    operator: Mapped[str] = mapped_column(String(8), default="")
    threshold: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    keywords: Mapped[Any] = mapped_column(JSON, default=list)
    severity: Mapped[str] = mapped_column(String(16), default="Medium")
    risk_points: Mapped[int] = mapped_column(Integer, default=20)
    guidance: Mapped[str] = mapped_column(Text, default="")
    preferred_language: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


# ─────────────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────────────

_engine: Any = None
_SessionLocal: Optional[sessionmaker] = None
_backend: str = "uninitialised"
_backend_error: Optional[str] = None

# Lives under the configured storage dir, which is correct both in a local
# checkout and inside the container (see config.BACKEND_DIR).
SQLITE_FALLBACK_PATH = settings.storage_dir / "dharma_fallback.db"


def init_db() -> str:
    """Connect (Postgres, else SQLite) and create the domain tables."""
    global _engine, _SessionLocal, _backend, _backend_error
    if _engine is not None:
        return _backend

    try:
        engine = create_engine(
            settings.sqlalchemy_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            future=True,
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        _engine = engine
        _backend = "postgresql"
        _backend_error = None
        logger.info("Connected to PostgreSQL.")
    except Exception as exc:
        _backend_error = f"{type(exc).__name__}: {exc}"
        logger.warning(
            "PostgreSQL unavailable (%s); falling back to SQLite at %s. "
            "Run `docker compose up -d postgres` for the full stack.",
            _backend_error,
            SQLITE_FALLBACK_PATH,
        )
        SQLITE_FALLBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            f"sqlite:///{SQLITE_FALLBACK_PATH.as_posix()}",
            connect_args={"check_same_thread": False},
            future=True,
        )
        _backend = "sqlite"

        # SQLite ships with foreign-key enforcement OFF. Leaving it off would make
        # the fallback silently accept writes that Postgres rejects — which is
        # exactly how an insert-ordering bug hid here once. Enforce it so both
        # backends fail the same way.
        @event.listens_for(_engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    Base.metadata.create_all(_engine)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _backend


def get_engine() -> Any:
    if _engine is None:
        init_db()
    return _engine


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional session: commits on success, rolls back on error."""
    if _SessionLocal is None:
        init_db()
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    with session_scope() as session:
        yield session


def db_health() -> Dict[str, Any]:
    if _engine is None:
        init_db()
    ok = True
    error = None
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        ok = False
        error = str(exc)
    return {
        "backend": _backend,
        "connected": ok,
        "error": error,
        "postgres_error": _backend_error,
        "sqlite_path": str(SQLITE_FALLBACK_PATH) if _backend == "sqlite" else None,
    }


def reset_db() -> None:
    """Drop and recreate the domain tables. Used by tests and `/api/demo/reset`."""
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
