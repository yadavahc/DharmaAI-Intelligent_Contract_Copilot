"""
Dharma AI agent layer — all Lyzr agent definitions live here.

Read in this order:

  1. `lyzr_compat.py`      Resolves the Lyzr runtime (real SDK, else a
                           signature-identical shim). Everything else imports
                           `Agent` / `Task` / `LinearSyncPipeline` from here.
  2. `model.py`            Dharma AI's implementation of Lyzr's `AIModel` ABC,
                           backed by the modern OpenAI SDK: JSON mode, streaming,
                           and per-call telemetry.
  3. `roles.py`            The canonical `Agent.role` strings.
  4. `base.py`             `DharmaAgent` — owns one Lyzr `Agent`, emits Lyzr
                           `Task`s, and parses structured results.
  5. `contract_agents.py`  The roster: all nine required agents plus the two
                           supporting agents behind the signature features.
  6. `pipeline.py`         Orchestration: the clause-review pipeline, a native
                           `LinearSyncPipeline`, and the two-agent negotiation loop.
  7. `heuristics.py`       Deterministic classification / risk logic used as the
                           fallback, as demo mode, and as the unit-test surface.
  8. `demo_fixtures.py`    Canned-but-input-sensitive output for demo mode.
"""

from app.agents.contract_agents import (  # noqa: F401
    AGENT_CLASSES,
    AuditAgent,
    ClauseClassificationAgent,
    ContractParsingAgent,
    CounterpartyNegotiatorAgent,
    EscalationAgent,
    ExecutiveSummaryAgent,
    NegotiationStrategyCoachAgent,
    OrganizationNegotiatorAgent,
    PlaybookValidationAgent,
    RedlineAgent,
    RiskAssessmentAgent,
    agent_roster,
    get_agent,
)
from app.agents.lyzr_compat import (  # noqa: F401
    LYZR_RUNTIME,
    LYZR_VERSION,
    Agent,
    LinearSyncPipeline,
    Task,
    runtime_info,
)
from app.agents.pipeline import (  # noqa: F401
    NegotiationOrchestrator,
    run_clause_review_pipeline,
    run_lyzr_linear_pipeline,
)

__all__ = [
    "AGENT_CLASSES",
    "Agent",
    "LinearSyncPipeline",
    "LYZR_RUNTIME",
    "LYZR_VERSION",
    "NegotiationOrchestrator",
    "Task",
    "agent_roster",
    "get_agent",
    "run_clause_review_pipeline",
    "run_lyzr_linear_pipeline",
    "runtime_info",
]
