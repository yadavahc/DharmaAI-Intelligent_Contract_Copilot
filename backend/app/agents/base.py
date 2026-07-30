"""
Base class shared by all nine Dharma AI agents.

Every agent is a genuine Lyzr agent. `DharmaAgent` holds a `lyzr_compat.Agent`
(role + prompt_persona) and emits `lyzr_compat.Task` objects, so an agent can be
either:

  * run on its own via `run_json()` / `run_text()`, or
  * dropped into a `LinearSyncPipeline` via `build_task()` for multi-step
    orchestration with Lyzr's own task chaining.

Both routes execute through the same `Task.execute()`, so there is no
"real Lyzr path" and separate "shortcut path" — the pipeline in `pipeline.py`
and a solo call share one code path.

Subclasses declare four things:
    role          — Lyzr `Agent.role`, the agent's identity
    persona       — Lyzr `Agent.prompt_persona`, its voice and priorities
    instructions  — Lyzr `Task.instructions`, what this step must do
    schema_hint   — the JSON shape expected back (None for prose agents)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.agents.lyzr_compat import Agent, OutputType, Task
from app.agents.model import (
    DharmaOpenAIModel,
    extract_json,
    get_model,
    model_for_agent,
)


@dataclass
class AgentCard:
    """Introspection payload for `GET /api/agents` — what each agent is for."""

    key: str
    name: str
    role: str
    persona: str
    instructions: str
    outputs: str
    hands_off_to: List[str] = field(default_factory=list)
    uses_qdrant: bool = False
    qdrant_purpose: Optional[str] = None


class DharmaAgent:
    """Wraps one Lyzr `Agent` and knows how to build its Lyzr `Task`."""

    key: str = "agent"
    name: str = "Agent"
    role: str = "Agent"
    persona: str = ""
    instructions: str = ""
    schema_hint: Optional[str] = None
    outputs: str = ""
    hands_off_to: List[str] = []
    uses_qdrant: bool = False
    qdrant_purpose: Optional[str] = None
    temperature: float = 0.2

    def __init__(self, model: Optional[DharmaOpenAIModel] = None):
        # One model instance per agent, pre-bound to this agent's role, temperature
        # and JSON mode. Because Lyzr spreads the model's `parameters` into the
        # OpenAI call, JSON-mode agents get strict JSON straight out of
        # `Task.execute()` — no bypass needed.
        self.model = model or model_for_agent(
            agent_role=self.role,
            task_name=self.key,
            temperature=self.temperature,
            json_mode=self.schema_hint is not None,
        )
        # The actual Lyzr Agent object.
        self.lyzr_agent: Agent = Agent(role=self.role, prompt_persona=self.persona)

    # ── Lyzr wiring ────────────────────────────────────────────────────────
    def _instructions_for(self, instructions: Optional[str] = None) -> str:
        """Append the JSON contract for agents running in JSON mode.

        This is not merely a prompting nicety. OpenAI **rejects** a request with
        `response_format={"type":"json_object"}` unless the messages contain the
        literal word "json":

            400 — 'messages' must contain the word 'json' in some form,
                  to use 'response_format' of type 'json_object'

        Because JSON mode is set on the model's `parameters` (which is what makes
        a plain `Task.execute()` return strict JSON), *every* path that builds a
        task has to satisfy that requirement — the pipeline route as much as the
        direct route. Centralising it here is what keeps them consistent; when it
        lived only in `run_json`, the native `LinearSyncPipeline` route 400'd
        against the live API while demo mode happily passed.
        """
        instr = instructions or self.instructions
        if self.schema_hint and "json" not in instr.lower():
            instr = (
                f"{instr}. Respond with a single valid JSON object only — no prose, "
                f"no markdown fence. Conform to this shape: {self.schema_hint}"
            )
        return instr

    def build_task(
        self,
        default_input: str = "",
        *,
        instructions: Optional[str] = None,
        input_tasks: Optional[List[Task]] = None,
        log_output: bool = False,
        name: Optional[str] = None,
    ) -> Task:
        """Create the Lyzr `Task` for this agent, ready for a pipeline."""
        return Task(
            model=self.model,
            agent=self.lyzr_agent,
            instructions=self._instructions_for(instructions),
            default_input=default_input,
            name=name or self.key,
            output_type=OutputType.TEXT,
            input_tasks=input_tasks,
            log_output=log_output,
            # Lyzr interpolates `previous_output` into the prompt unconditionally
            # (`f"... Input: {previous_output} {default_input}"`). Left at its
            # default of None, a standalone task emits the literal "Input: None
            # {...}". Empty string keeps the prompt clean; a pipeline overwrites
            # this with the upstream task's real output.
            previous_output="",
        )

    # Lyzr composes these two strings internally; we rebuild them identically
    # for the direct (non-pipeline) calls so prompts are byte-identical either way.
    def _system_persona(self) -> str:
        return (
            f"In your role as {self.role}, you embody a persona defined by "
            f"{self.persona}."
        )

    def _prompt(self, payload: str, instructions: Optional[str] = None) -> str:
        return (
            f"Now execute these instructions: {self._instructions_for(instructions)}."
            f"  Input: {payload}"
        )

    # ── Execution ──────────────────────────────────────────────────────────
    def run_text(self, payload: str, *, instructions: Optional[str] = None) -> str:
        """Run this agent through a real Lyzr `Task` and return its raw text."""
        task = self.build_task(default_input=payload, instructions=instructions)
        return task.execute() or ""

    def run_json(
        self,
        payload: str,
        *,
        instructions: Optional[str] = None,
        fallback: Optional[Any] = None,
    ) -> Any:
        """Run this agent through a real Lyzr `Task` and parse the result as JSON.

        The schema contract is appended to the instructions Lyzr passes through, so
        the requirement travels inside the Lyzr task rather than around it. If the
        response will not parse, `generate_json` performs one repair pass and then
        returns `fallback` — an agent that cannot produce clean JSON degrades and is
        flagged low-confidence downstream, rather than aborting the pipeline.
        """
        # `build_task` applies the JSON contract via `_instructions_for`, so the
        # requirement is satisfied identically here and on the pipeline route.
        task = self.build_task(default_input=payload, instructions=instructions)
        try:
            raw = task.execute() or ""
        except Exception:
            return fallback

        parsed = extract_json(raw)
        if parsed is not None:
            return parsed

        # One repair attempt, then give up gracefully.
        return self.model.generate_json(
            system_persona="You convert malformed text into strict JSON.",
            prompt=(
                "The following was supposed to be a single valid JSON object but did "
                f"not parse. Return only the corrected JSON.\n\n---\n{raw[:4000]}\n---"
            ),
            agent_role=f"{self.role}:json-repair",
            task_name=self.key,
            fallback=fallback,
            temperature=0.0,
        )

    def stream(self, payload: str, *, instructions: Optional[str] = None):
        """Stream deltas — used by the negotiators in the Live Agent Theater."""
        return self.model.stream_text(
            system_persona=self._system_persona(),
            prompt=self._prompt(payload, instructions),
            agent_role=self.role,
            task_name=self.key,
            temperature=self.temperature,
        )

    # ── Introspection ──────────────────────────────────────────────────────
    @classmethod
    def card(cls) -> AgentCard:
        return AgentCard(
            key=cls.key,
            name=cls.name,
            role=cls.role,
            persona=cls.persona,
            instructions=cls.instructions,
            outputs=cls.outputs,
            hands_off_to=list(cls.hands_off_to),
            uses_qdrant=cls.uses_qdrant,
            qdrant_purpose=cls.qdrant_purpose,
        )


def clamp(value: Any, low: float, high: float, default: float) -> float:
    """Coerce untrusted model numerics into range. Used by every scoring agent."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return default
    if n != n:  # NaN
        return default
    return max(low, min(high, n))
