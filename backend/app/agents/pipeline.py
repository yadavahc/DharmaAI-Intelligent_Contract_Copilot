"""
Agent orchestration.

Two orchestration shapes, both built from the same agents:

* `run_clause_review_pipeline` — the production ingest path for one clause:
  classify → validate against playbook → assess risk → draft redline. Each step
  executes as a Lyzr `Task`; typed results are passed forward so downstream
  agents receive real structure rather than a stringified blob.

* `build_lyzr_linear_pipeline` / `run_lyzr_linear_pipeline` — the same agents
  assembled into a genuine `LinearSyncPipeline` with `input_tasks` wiring, so
  Lyzr's own chaining and task logging drive execution. Exposed at
  `POST /api/agents/pipeline/demo` so a reviewer can watch the framework work.

Plus `NegotiationOrchestrator`, the two-agent adversarial loop that drives the
Live Agent Theater. It is a generator of events, which is what lets the same
code serve both a blocking call and an SSE stream.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterator, List, Optional

from app.agents.contract_agents import (
    ClauseClassificationAgent,
    CounterpartyNegotiatorAgent,
    EscalationAgent,
    NegotiationStrategyCoachAgent,
    OrganizationNegotiatorAgent,
    PlaybookValidationAgent,
    RedlineAgent,
    RiskAssessmentAgent,
    get_agent,
)
from app.agents.lyzr_compat import LinearSyncPipeline, Task
from app.config import settings
from app.domain import NegotiationOutcome, RiskLevel

# ─────────────────────────────────────────────────────────────────────────────
# Clause review pipeline
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ClauseReviewResult:
    clause_id: Optional[str] = None
    heading: str = ""
    text: str = ""
    classification: Dict[str, Any] = field(default_factory=dict)
    playbook: Dict[str, Any] = field(default_factory=dict)
    risk: Dict[str, Any] = field(default_factory=dict)
    redline: Dict[str, Any] = field(default_factory=dict)
    escalation: Dict[str, Any] = field(default_factory=dict)
    agent_trace: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "clause_id": self.clause_id,
            "heading": self.heading,
            "text": self.text,
            "category": self.classification.get("category"),
            "confidence": self.classification.get("confidence"),
            "classification": self.classification,
            "playbook": self.playbook,
            "risk_score": self.risk.get("risk_score"),
            "risk_level": self.risk.get("risk_level"),
            "explanation": self.risk.get("explanation"),
            "suggested_fix": self.risk.get("suggested_fix"),
            "risk": self.risk,
            "redline": self.redline,
            "escalation": self.escalation,
            "agent_trace": self.agent_trace,
        }


def run_clause_review_pipeline(
    clause_text: str,
    *,
    heading: str = "",
    clause_id: Optional[str] = None,
    playbook_rules: Optional[List[Dict[str, Any]]] = None,
    similar_clauses: Optional[List[Dict[str, Any]]] = None,
    precedents: Optional[List[Dict[str, Any]]] = None,
    include_redline: bool = True,
    include_escalation: bool = True,
    on_step: Optional[Callable[[str, Dict[str, Any]], None]] = None,
) -> ClauseReviewResult:
    """Run the four ingest agents over one clause, handing off typed results.

    `playbook_rules`, `similar_clauses` and `precedents` are Qdrant retrievals
    supplied by the caller (see `services/qdrant_store.py`) — the agents consume
    retrieval results, they do not perform retrieval themselves.
    """
    result = ClauseReviewResult(clause_id=clause_id, heading=heading, text=clause_text)
    rules = playbook_rules or []

    def _step(name: str, payload: Dict[str, Any], started: float) -> None:
        entry = {
            "agent": name,
            "duration_ms": round((time.time() - started) * 1000, 1),
            "confidence": payload.get("confidence"),
        }
        result.agent_trace.append(entry)
        if on_step is not None:
            on_step(name, payload)

    # 1 ─ classify
    t0 = time.time()
    classifier: ClauseClassificationAgent = get_agent("clause_classification")  # type: ignore[assignment]
    result.classification = classifier.classify(clause_text, heading=heading)
    _step("clause_classification", result.classification, t0)
    category = result.classification.get("category") or "Other"

    # 2 ─ validate against the retrieved playbook
    t0 = time.time()
    validator: PlaybookValidationAgent = get_agent("playbook_validation")  # type: ignore[assignment]
    result.playbook = validator.validate(clause_text, category, rules)
    _step("playbook_validation", result.playbook, t0)

    # 3 ─ score risk
    t0 = time.time()
    assessor: RiskAssessmentAgent = get_agent("risk_assessment")  # type: ignore[assignment]
    result.risk = assessor.assess(
        clause_text,
        category,
        playbook_rules=rules,
        similar_clauses=similar_clauses,
    )
    _step("risk_assessment", result.risk, t0)

    # 4 ─ redline (only where there is something to fix)
    if include_redline and result.risk.get("risk_level") != RiskLevel.LOW.value:
        t0 = time.time()
        redliner: RedlineAgent = get_agent("redline")  # type: ignore[assignment]
        result.redline = redliner.draft(
            clause_text,
            category,
            risk_explanation=str(result.risk.get("explanation") or ""),
            suggested_fix=str(result.risk.get("suggested_fix") or ""),
            precedents=precedents,
            risk_level=str(result.risk.get("risk_level") or RiskLevel.MEDIUM.value),
        )
        _step("redline", result.redline, t0)

    # 5 ─ escalation triage
    if include_escalation:
        t0 = time.time()
        escalator: EscalationAgent = get_agent("escalation")  # type: ignore[assignment]
        unresolved = [
            str(v.get("rule_id"))
            for v in (result.playbook.get("violations") or [])
            if v.get("rule_id")
        ]
        result.escalation = escalator.triage(
            clause_text,
            category,
            risk_score=float(result.risk.get("risk_score") or 0),
            risk_level=str(result.risk.get("risk_level") or RiskLevel.LOW.value),
            deadlocked=False,
            unresolved_rules=unresolved,
            agent_confidence=min(
                float(result.classification.get("confidence") or 1.0),
                float(result.risk.get("confidence") or 1.0),
            ),
        )
        _step("escalation", result.escalation, t0)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Native Lyzr LinearSyncPipeline
# ─────────────────────────────────────────────────────────────────────────────


def build_lyzr_linear_pipeline(
    clause_text: str,
    *,
    heading: str = "",
    playbook_rules: Optional[List[Dict[str, Any]]] = None,
    log_output: bool = True,
) -> LinearSyncPipeline:
    """Assemble the ingest agents into a genuine Lyzr `LinearSyncPipeline`.

    Demonstrates Lyzr's native orchestration: tasks run in declared order, and
    `input_tasks` makes each task's prompt include the named upstream task's
    output. `Task` is text-in/text-out by design, so this route yields the
    framework's own chaining and logging rather than typed handoffs — which is
    exactly what makes it a useful thing to show a judge.
    """
    rules = playbook_rules or []
    classifier = get_agent("clause_classification")
    validator = get_agent("playbook_validation")
    assessor = get_agent("risk_assessment")
    redliner = get_agent("redline")

    clause_payload = json.dumps(
        {"heading": heading, "clause_text": clause_text[:3000]}, ensure_ascii=False
    )
    rules_payload = json.dumps({"playbook_rules": rules[:8]}, ensure_ascii=False)

    classify_task: Task = classifier.build_task(
        default_input=clause_payload, name="1-classify", log_output=log_output
    )
    validate_task: Task = validator.build_task(
        default_input=f"{clause_payload} {rules_payload}",
        name="2-playbook",
        input_tasks=[classify_task],
        log_output=log_output,
    )
    assess_task: Task = assessor.build_task(
        default_input=f"{clause_payload} {rules_payload}",
        name="3-risk",
        input_tasks=[classify_task, validate_task],
        log_output=log_output,
    )
    redline_task: Task = redliner.build_task(
        default_input=clause_payload,
        name="4-redline",
        input_tasks=[assess_task],
        log_output=log_output,
    )

    return LinearSyncPipeline(
        tasks=[classify_task, validate_task, assess_task, redline_task],
        name="dharma-clause-review",
        completion_message="Dharma AI clause review pipeline complete.",
    )


def run_lyzr_linear_pipeline(
    clause_text: str,
    *,
    heading: str = "",
    playbook_rules: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Run the native pipeline and return its per-task output."""
    from app.agents.lyzr_compat import runtime_info
    from app.agents.model import extract_json

    pipeline = build_lyzr_linear_pipeline(
        clause_text, heading=heading, playbook_rules=playbook_rules
    )
    started = time.time()
    raw_output = pipeline.run()

    tasks: List[Dict[str, Any]] = []
    for task, entry in zip(pipeline.tasks, raw_output):
        text = str(entry.get("task_output") or "")
        tasks.append(
            {
                "task_name": str(task.name),
                "task_id": str(entry.get("task_id")),
                "agent_role": task.agent.role,
                "agent_persona": task.agent.prompt_persona[:200],
                "instructions": task.instructions[:300],
                "input_tasks": [str(t.name) for t in (task.input_tasks or [])],
                "output_parsed": extract_json(text),
                "output_raw": text[:2000],
            }
        )

    return {
        "pipeline_name": pipeline.name,
        "pipeline_class": (
            f"{type(pipeline).__module__}.{type(pipeline).__qualname__}"
        ),
        "runtime": runtime_info(),
        "duration_ms": round((time.time() - started) * 1000, 1),
        "task_count": len(tasks),
        "tasks": tasks,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Two-agent negotiation loop
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class NegotiationTurn:
    round: int
    side: str  # "organization" | "counterparty"
    agent_role: str
    message: str
    stance: str
    proposed_language: str
    concession: str
    rationale: str
    projected_risk_score: float
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


class NegotiationOrchestrator:
    """Runs Organization vs Counterparty for N rounds and decides the outcome.

    Emitted as a generator of events so one implementation serves both the
    blocking endpoint and the SSE stream behind the Live Agent Theater. Event
    types: `start`, `thinking`, `turn`, `coach`, `risk`, `outcome`, `escalation`,
    `done`, `error`.
    """

    def __init__(
        self,
        clause_text: str,
        category: str,
        *,
        initial_risk: float,
        max_rounds: Optional[int] = None,
        playbook_rules: Optional[List[Dict[str, Any]]] = None,
        memory: Optional[List[Dict[str, Any]]] = None,
        include_coach: bool = True,
    ):
        self.clause_text = clause_text
        self.category = category
        self.initial_risk = initial_risk
        self.max_rounds = max_rounds or settings.negotiation_max_rounds
        self.playbook_rules = playbook_rules or []
        self.memory = memory or []
        self.include_coach = include_coach

        self.org: OrganizationNegotiatorAgent = get_agent("organization_negotiator")  # type: ignore[assignment]
        self.counterparty: CounterpartyNegotiatorAgent = get_agent("counterparty_negotiator")  # type: ignore[assignment]
        self.coach: NegotiationStrategyCoachAgent = get_agent("strategy_coach")  # type: ignore[assignment]
        self.escalator: EscalationAgent = get_agent("escalation")  # type: ignore[assignment]

        self.history: List[Dict[str, Any]] = []
        self.current_risk = initial_risk
        self.outcome = NegotiationOutcome.PENDING.value
        self.final_language = clause_text

    # ── event stream ───────────────────────────────────────────────────────
    def stream(self) -> Iterator[Dict[str, Any]]:
        yield {
            "type": "start",
            "category": self.category,
            "max_rounds": self.max_rounds,
            "initial_risk_score": round(self.initial_risk, 1),
            "clause_preview": self.clause_text[:280],
            "agents": {
                "organization": {
                    "role": self.org.role,
                    "persona": self.org.persona[:200],
                },
                "counterparty": {
                    "role": self.counterparty.role,
                    "persona": self.counterparty.persona[:200],
                },
            },
        }

        try:
            for round_no in range(1, self.max_rounds + 1):
                accepted = False

                for side, agent in (
                    ("organization", self.org),
                    ("counterparty", self.counterparty),
                ):
                    yield {
                        "type": "thinking",
                        "round": round_no,
                        "side": side,
                        "agent_role": agent.role,
                    }

                    turn_data = agent.negotiate(
                        self.final_language,
                        self.category,
                        round_no=round_no,
                        max_rounds=self.max_rounds,
                        history=self.history,
                        current_risk=self.current_risk,
                        memory=self.memory,
                        playbook_rules=self.playbook_rules,
                    )

                    turn = NegotiationTurn(
                        round=round_no,
                        side=side,
                        agent_role=agent.role,
                        message=turn_data["message"],
                        stance=turn_data["stance"],
                        proposed_language=turn_data["proposed_language"],
                        concession=turn_data["concession"],
                        rationale=turn_data["rationale"],
                        projected_risk_score=float(turn_data["projected_risk_score"]),
                        confidence=float(turn_data["confidence"]),
                    )
                    self.history.append(turn.to_dict())

                    # Only our own side's language is adopted as the working text;
                    # the counterparty's proposal is a position, not our draft.
                    if side == "organization" and turn.proposed_language.strip():
                        self.final_language = turn.proposed_language

                    previous_risk = self.current_risk
                    self.current_risk = turn.projected_risk_score

                    yield {"type": "turn", **turn.to_dict()}
                    yield {
                        "type": "risk",
                        "round": round_no,
                        "risk_score": round(self.current_risk, 1),
                        "delta": round(self.current_risk - previous_risk, 1),
                    }

                    if self.include_coach and side == "organization":
                        coaching = self.coach.coach(
                            self.clause_text,
                            self.category,
                            round_no=round_no,
                            history=self.history,
                            proposed_redline=turn.proposed_language,
                            current_risk=self.current_risk,
                            memory=self.memory,
                        )
                        yield {"type": "coach", "round": round_no, **coaching}

                    if turn.stance == "accept":
                        accepted = True
                    elif turn.stance == "reject":
                        self.outcome = NegotiationOutcome.REJECTED.value
                        yield {
                            "type": "outcome",
                            "outcome": self.outcome,
                            "round": round_no,
                            "reason": f"{agent.role} rejected the clause outright.",
                        }
                        break
                    elif turn.stance == "escalate":
                        self.outcome = NegotiationOutcome.ESCALATED.value
                        yield {
                            "type": "outcome",
                            "outcome": self.outcome,
                            "round": round_no,
                            "reason": f"{agent.role} requested human escalation.",
                        }
                        break

                if self.outcome != NegotiationOutcome.PENDING.value:
                    break

                # Both sides accepted in the same round → settled.
                if accepted and self._both_accepted_this_round(round_no):
                    self.outcome = NegotiationOutcome.ACCEPTED.value
                    yield {
                        "type": "outcome",
                        "outcome": self.outcome,
                        "round": round_no,
                        "reason": "Both agents accepted the same position.",
                    }
                    break

            # Ran out of rounds without agreement.
            if self.outcome == NegotiationOutcome.PENDING.value:
                self.outcome = NegotiationOutcome.ESCALATED.value
                yield {
                    "type": "outcome",
                    "outcome": self.outcome,
                    "round": self.max_rounds,
                    "reason": (
                        f"Deadlocked after {self.max_rounds} rounds without agreement."
                    ),
                }

            # Escalation triage on the settled/deadlocked position.
            deadlocked = self.outcome == NegotiationOutcome.ESCALATED.value
            triage = self.escalator.triage(
                self.final_language,
                self.category,
                risk_score=self.current_risk,
                risk_level=(
                    RiskLevel.HIGH.value
                    if self.current_risk >= settings.risk_high_threshold
                    else RiskLevel.MEDIUM.value
                ),
                deadlocked=deadlocked,
                unresolved_rules=[],
                agent_confidence=(
                    min(float(h.get("confidence") or 1.0) for h in self.history)
                    if self.history
                    else 1.0
                ),
            )
            yield {"type": "escalation", **triage}

            yield {
                "type": "done",
                "outcome": self.outcome,
                "rounds_used": (
                    max(h["round"] for h in self.history) if self.history else 0
                ),
                "final_risk_score": round(self.current_risk, 1),
                "initial_risk_score": round(self.initial_risk, 1),
                "risk_reduction": round(self.initial_risk - self.current_risk, 1),
                "final_language": self.final_language,
                "requires_human_approval": True,
                "escalated": triage.get("should_escalate", False),
                "turn_count": len(self.history),
            }

        except Exception as exc:  # keep the stream well-formed on failure
            yield {
                "type": "error",
                "error": f"{type(exc).__name__}: {exc}",
                "outcome": NegotiationOutcome.ESCALATED.value,
            }

    def _both_accepted_this_round(self, round_no: int) -> bool:
        stances = [
            h["stance"] for h in self.history if h["round"] == round_no
        ]
        return len(stances) == 2 and all(s == "accept" for s in stances)

    def run(self) -> Dict[str, Any]:
        """Blocking variant: drain the stream and return the collected result."""
        events = list(self.stream())
        done = next(
            (e for e in reversed(events) if e.get("type") in ("done", "error")), {}
        )
        return {
            "outcome": self.outcome,
            "turns": self.history,
            "events": events,
            "summary": done,
        }
