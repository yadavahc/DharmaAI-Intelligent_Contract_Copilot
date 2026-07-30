"""
Dharma AI's implementation of Lyzr's `AIModel` ABC.

Lyzr's `Task` accepts any `AIModel`, so implementing that one ABC is the
supported extension point for teaching the whole framework new tricks. We do it
because the SDK's bundled `OpenAIModel` is text-only, synchronous, and pinned to
`openai==1.3.4`. Dharma AI needs three things it cannot give us:

  1. **Structured output.** Clause classification, risk scoring and redlines are
     consumed as typed JSON, not prose. `response_format={"type":"json_object"}`
     plus a repair pass beats regex-scraping model prose.
  2. **Streaming.** The Live Agent Theater renders negotiation tokens as they
     arrive; `generate_text` alone cannot express that.
  3. **Observability.** Every call is recorded (agent role, latency, tokens,
     truncated prompt/response) so the Audit Agent has real data and judges can
     see the multi-agent traffic.

`generate_text()` keeps Lyzr's exact signature, so `Task`/`LinearSyncPipeline`
drive this class with no adaptation. `generate_json()` and `stream_text()` are
additive, used by Dharma AI's own agent wrappers.
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterator, List, Optional

from app.agents.lyzr_compat import AIModel
from app.config import settings

# ─────────────────────────────────────────────────────────────────────────────
# Call telemetry — feeds the Audit Agent and /api/agents/telemetry
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class LLMCall:
    call_id: str
    agent_role: str
    task_name: Optional[str]
    model: str
    started_at: float
    duration_ms: float
    prompt_chars: int
    response_chars: int
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    demo_mode: bool = False
    error: Optional[str] = None
    system_persona_preview: str = ""
    prompt_preview: str = ""
    response_preview: str = ""


class CallRecorder:
    """Bounded in-memory ring of recent LLM calls (thread-safe)."""

    def __init__(self, capacity: int = 400):
        self._capacity = capacity
        self._calls: List[LLMCall] = []
        self._lock = threading.Lock()

    def record(self, call: LLMCall) -> None:
        with self._lock:
            self._calls.append(call)
            if len(self._calls) > self._capacity:
                self._calls = self._calls[-self._capacity :]

    def recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            return [c.__dict__.copy() for c in reversed(self._calls[-limit:])]

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            calls = list(self._calls)
        if not calls:
            return {
                "total_calls": 0,
                "total_prompt_tokens": 0,
                "total_completion_tokens": 0,
                "avg_duration_ms": 0.0,
                "errors": 0,
                "by_agent": {},
            }
        by_agent: Dict[str, int] = {}
        for c in calls:
            by_agent[c.agent_role] = by_agent.get(c.agent_role, 0) + 1
        return {
            "total_calls": len(calls),
            "total_prompt_tokens": sum(c.prompt_tokens or 0 for c in calls),
            "total_completion_tokens": sum(c.completion_tokens or 0 for c in calls),
            "avg_duration_ms": round(sum(c.duration_ms for c in calls) / len(calls), 1),
            "errors": sum(1 for c in calls if c.error),
            "by_agent": by_agent,
        }


recorder = CallRecorder()


# ─────────────────────────────────────────────────────────────────────────────
# JSON extraction helpers
# ─────────────────────────────────────────────────────────────────────────────

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_json(text: str) -> Optional[Any]:
    """Best-effort structured parse of model output.

    Tries, in order: the whole string; a fenced ```json block; the widest
    balanced {...} or [...] span. Returns None if nothing parses, letting the
    caller fall back rather than raising mid-pipeline.
    """
    if not text:
        return None
    candidates: List[str] = [text.strip()]

    for m in _FENCE_RE.finditer(text):
        candidates.append(m.group(1).strip())

    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            candidates.append(text[start : end + 1])

    for cand in candidates:
        try:
            return json.loads(cand)
        except (json.JSONDecodeError, ValueError):
            continue
    return None


# ─────────────────────────────────────────────────────────────────────────────
# The model
# ─────────────────────────────────────────────────────────────────────────────


class DharmaOpenAIModel(AIModel):
    """Concrete `AIModel` for Lyzr, backed by the modern OpenAI SDK.

    Parameters mirror Lyzr's `OpenAIModel(api_key, parameters)` convention:
    `parameters` is spread straight into `chat.completions.create(...)`.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        demo_handler: Optional[Callable[[str, str], str]] = None,
        default_agent_role: str = "unspecified-agent",
        default_task_name: Optional[str] = None,
    ):
        self.parameters: Dict[str, Any] = parameters or {
            "model": settings.openai_model,
            "temperature": 0.2,
        }
        self.api_key = api_key or settings.openai_api_key
        self.demo_mode = settings.demo_mode
        self._demo_handler = demo_handler
        # Lyzr's `Task` calls `generate_text(task_id, system_persona, prompt)` with
        # no way to pass telemetry metadata. Binding the role to the model instance
        # (one instance per agent) keeps audit attribution intact when a call
        # arrives via `Task.execute()` rather than directly.
        self.default_agent_role = default_agent_role
        self.default_task_name = default_task_name
        self._client: Any = None
        self._client_lock = threading.Lock()

    # -- lazily construct the client so import never requires a key ----------
    @property
    def client(self) -> Any:
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    from openai import OpenAI

                    self._client = OpenAI(
                        api_key=self.api_key,
                        timeout=settings.openai_timeout_seconds,
                    )
        return self._client

    # ── Lyzr AIModel interface ─────────────────────────────────────────────
    def generate_text(
        self,
        task_id: Any = None,
        system_persona: Optional[str] = None,
        prompt: Optional[str] = None,
        messages: Optional[List[dict]] = None,
        **kwargs: Any,
    ) -> str:
        """Signature-compatible with `lyzr_automata`'s `OpenAIModel.generate_text`.

        `**kwargs` absorbs the `tasks` argument named in the `AIModel` ABC but
        never passed by `Task`, so both call styles work.
        """
        agent_role = kwargs.pop("agent_role", None) or self.default_agent_role
        task_name = kwargs.pop("task_name", None) or self.default_task_name
        response_format = kwargs.pop("response_format", None)
        # `Task` names its ABC arg `tasks`; accept and discard it.
        kwargs.pop("tasks", None)

        if messages is None:
            messages = [
                {"role": "system", "content": system_persona or ""},
                {"role": "user", "content": prompt or ""},
            ]

        prompt_chars = sum(len(m.get("content") or "") for m in messages)
        started = time.time()
        call_id = str(uuid.uuid4())

        if self.demo_mode:
            text = self._demo_response(system_persona or "", prompt or "", messages)
            duration = (time.time() - started) * 1000
            recorder.record(
                LLMCall(
                    call_id=call_id,
                    agent_role=agent_role,
                    task_name=task_name,
                    model=f"{self.parameters.get('model')} (demo)",
                    started_at=started,
                    duration_ms=round(duration, 1),
                    prompt_chars=prompt_chars,
                    response_chars=len(text),
                    demo_mode=True,
                    system_persona_preview=(system_persona or "")[:240],
                    prompt_preview=(prompt or "")[:400],
                    response_preview=text[:400],
                )
            )
            return text

        params = dict(self.parameters)
        params.update(kwargs)
        if response_format is not None:
            params["response_format"] = response_format

        try:
            response = self.client.chat.completions.create(**params, messages=messages)
            text = response.choices[0].message.content or ""
            usage = getattr(response, "usage", None)
            recorder.record(
                LLMCall(
                    call_id=call_id,
                    agent_role=agent_role,
                    task_name=task_name,
                    model=str(params.get("model")),
                    started_at=started,
                    duration_ms=round((time.time() - started) * 1000, 1),
                    prompt_chars=prompt_chars,
                    response_chars=len(text),
                    prompt_tokens=getattr(usage, "prompt_tokens", None),
                    completion_tokens=getattr(usage, "completion_tokens", None),
                    system_persona_preview=(system_persona or "")[:240],
                    prompt_preview=(prompt or "")[:400],
                    response_preview=text[:400],
                )
            )
            return text
        except Exception as exc:
            recorder.record(
                LLMCall(
                    call_id=call_id,
                    agent_role=agent_role,
                    task_name=task_name,
                    model=str(params.get("model")),
                    started_at=started,
                    duration_ms=round((time.time() - started) * 1000, 1),
                    prompt_chars=prompt_chars,
                    response_chars=0,
                    error=f"{type(exc).__name__}: {exc}",
                    system_persona_preview=(system_persona or "")[:240],
                    prompt_preview=(prompt or "")[:400],
                )
            )
            raise

    def generate_image(
        self, task_id: Any = None, prompt: str = "", resource_box: Any = None, **kwargs: Any
    ):
        """Required by the ABC. Dharma AI is text-only; images are out of scope."""
        raise NotImplementedError("Dharma AI agents do not generate images.")

    # ── Dharma AI extensions ───────────────────────────────────────────────
    def generate_json(
        self,
        system_persona: str,
        prompt: str,
        *,
        agent_role: str = "unspecified-agent",
        task_name: Optional[str] = None,
        schema_hint: Optional[str] = None,
        fallback: Optional[Any] = None,
        temperature: Optional[float] = None,
    ) -> Any:
        """Return parsed JSON, with a repair retry and a typed fallback.

        Never raises on malformed output: an agent that cannot produce clean
        JSON degrades to `fallback` and is flagged low-confidence downstream by
        the hallucination guardrail, rather than aborting the pipeline.
        """
        instruction = prompt
        if schema_hint:
            instruction = (
                f"{prompt}\n\nRespond with a single valid JSON object only — no "
                f"prose, no markdown fence. Conform to this shape:\n{schema_hint}"
            )

        kwargs: Dict[str, Any] = {
            "agent_role": agent_role,
            "task_name": task_name,
            "response_format": {"type": "json_object"},
        }
        if temperature is not None:
            kwargs["temperature"] = temperature

        try:
            raw = self.generate_text(
                system_persona=system_persona, prompt=instruction, **kwargs
            )
        except Exception:
            return fallback

        parsed = extract_json(raw)
        if parsed is not None:
            return parsed

        # One repair attempt: hand the model its own bad output back.
        try:
            repaired = self.generate_text(
                system_persona="You convert malformed text into strict JSON.",
                prompt=(
                    "The following was supposed to be a single valid JSON object "
                    "but did not parse. Return only the corrected JSON, nothing "
                    f"else.\n\n---\n{raw[:4000]}\n---"
                ),
                agent_role=f"{agent_role}:json-repair",
                task_name=task_name,
                response_format={"type": "json_object"},
                temperature=0,
            )
            parsed = extract_json(repaired)
        except Exception:
            parsed = None

        return parsed if parsed is not None else fallback

    def stream_text(
        self,
        system_persona: str,
        prompt: str,
        *,
        agent_role: str = "unspecified-agent",
        task_name: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> Iterator[str]:
        """Yield text deltas. Powers the Live Agent Theater's typing effect."""
        messages = [
            {"role": "system", "content": system_persona},
            {"role": "user", "content": prompt},
        ]
        started = time.time()
        call_id = str(uuid.uuid4())

        if self.demo_mode:
            text = self._demo_response(system_persona, prompt, messages)
            for chunk in _chunk_words(text):
                yield chunk
            recorder.record(
                LLMCall(
                    call_id=call_id,
                    agent_role=agent_role,
                    task_name=task_name,
                    model=f"{self.parameters.get('model')} (demo-stream)",
                    started_at=started,
                    duration_ms=round((time.time() - started) * 1000, 1),
                    prompt_chars=len(prompt),
                    response_chars=len(text),
                    demo_mode=True,
                    prompt_preview=prompt[:400],
                    response_preview=text[:400],
                )
            )
            return

        params = dict(self.parameters)
        if temperature is not None:
            params["temperature"] = temperature

        collected: List[str] = []
        try:
            stream = self.client.chat.completions.create(
                **params, messages=messages, stream=True
            )
            for event in stream:
                if not event.choices:
                    continue
                delta = event.choices[0].delta
                piece = getattr(delta, "content", None)
                if piece:
                    collected.append(piece)
                    yield piece
        except Exception as exc:
            recorder.record(
                LLMCall(
                    call_id=call_id,
                    agent_role=agent_role,
                    task_name=task_name,
                    model=str(params.get("model")),
                    started_at=started,
                    duration_ms=round((time.time() - started) * 1000, 1),
                    prompt_chars=len(prompt),
                    response_chars=len("".join(collected)),
                    error=f"{type(exc).__name__}: {exc}",
                    prompt_preview=prompt[:400],
                )
            )
            raise
        else:
            text = "".join(collected)
            recorder.record(
                LLMCall(
                    call_id=call_id,
                    agent_role=agent_role,
                    task_name=task_name,
                    model=str(params.get("model")),
                    started_at=started,
                    duration_ms=round((time.time() - started) * 1000, 1),
                    prompt_chars=len(prompt),
                    response_chars=len(text),
                    prompt_preview=prompt[:400],
                    response_preview=text[:400],
                )
            )

    # ── demo mode ──────────────────────────────────────────────────────────
    def _demo_response(
        self, system_persona: str, prompt: str, messages: List[dict]
    ) -> str:
        if self._demo_handler is not None:
            return self._demo_handler(system_persona, prompt)
        from app.agents.demo_fixtures import synthesize_demo_response

        return synthesize_demo_response(system_persona, prompt)


def _chunk_words(text: str, per_chunk: int = 3) -> Iterator[str]:
    """Split text into small pieces so demo streaming looks like real streaming."""
    words = text.split(" ")
    for i in range(0, len(words), per_chunk):
        piece = " ".join(words[i : i + per_chunk])
        yield piece if i + per_chunk >= len(words) else piece + " "


# ── shared singleton ───────────────────────────────────────────────────────
_default_model: Optional[DharmaOpenAIModel] = None
_default_lock = threading.Lock()


def get_model() -> DharmaOpenAIModel:
    global _default_model
    if _default_model is None:
        with _default_lock:
            if _default_model is None:
                _default_model = DharmaOpenAIModel()
    return _default_model


def model_for_agent(
    *,
    agent_role: str,
    task_name: str,
    temperature: float = 0.2,
    json_mode: bool = True,
) -> DharmaOpenAIModel:
    """Build the `AIModel` for one agent.

    Note `response_format` lives in `parameters`, which Lyzr spreads directly into
    `chat.completions.create(**parameters, messages=...)`. That is what lets a
    plain `Task.execute()` return strict JSON — so structured agents run through
    genuine Lyzr task execution instead of needing a side channel.
    """
    parameters: Dict[str, Any] = {
        "model": settings.openai_model,
        "temperature": temperature,
    }
    if json_mode:
        parameters["response_format"] = {"type": "json_object"}
    return DharmaOpenAIModel(
        parameters=parameters,
        default_agent_role=agent_role,
        default_task_name=task_name,
    )
