"""
Runtime error monitoring.

Unhandled exceptions in the agent pipeline are the failures that matter most —
they happen mid-review, often on one clause out of seventeen, and without
reporting they surface as "the demo froze" with nothing to debug from.

Sentry is supported but **optional**. Setting `SENTRY_DSN` enables it; leaving it
unset falls back to structured JSON logging that any log aggregator can ingest.
That keeps the repo runnable without a third-party signup while giving a real
production path — a hard `sentry-sdk` dependency would force everyone through an
account creation to run a hackathon demo.

Whatever the sink, three things always hold:

  * **Secrets are scrubbed before an event leaves the process.** An exception
    carrying a `DATABASE_URL` with a password, or a request body containing an
    API key, must not be shipped to a third party verbatim.
  * **Reporting never raises.** A monitoring outage must not become an
    application outage.
  * **Agent context is attached** — which agent, which clause, which contract —
    because "KeyError in contract_agents.py" is not actionable on its own.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import traceback
from typing import Any, Dict, Optional

logger = logging.getLogger("dharma.errors")

_sentry: Any = None
_initialised = False

# Patterns scrubbed from any payload before it leaves the process.
_SCRUB_KEYS = re.compile(
    r"(api[_-]?key|token|secret|password|passwd|authorization|dsn|credential)",
    re.IGNORECASE,
)
_SCRUB_VALUES = [
    # OpenAI-style keys
    (re.compile(r"sk-[A-Za-z0-9_\-]{16,}"), "sk-***REDACTED***"),
    # Bearer tokens and JWTs
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"), "***JWT***"),
    # Credentials embedded in a connection URI
    (re.compile(r"(://)[^:/@\s]+:[^@/\s]+@"), r"\1***:***@"),
]


def scrub(value: Any) -> Any:
    """Recursively redact secrets from a payload before reporting it."""
    if isinstance(value, dict):
        return {
            k: ("***REDACTED***" if _SCRUB_KEYS.search(str(k)) else scrub(v))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [scrub(v) for v in value]
    if isinstance(value, str):
        text = value
        for pattern, replacement in _SCRUB_VALUES:
            text = pattern.sub(replacement, text)
        return text
    return value


def init_error_monitoring(release: str = "dharma-ai") -> Dict[str, Any]:
    """Initialise Sentry if a DSN is configured. Safe to call more than once."""
    global _sentry, _initialised

    if _initialised:
        return status()
    _initialised = True

    dsn = (os.environ.get("SENTRY_DSN") or "").strip()
    if not dsn:
        logger.info(
            "SENTRY_DSN not set — unhandled errors are reported to structured logs. "
            "Set SENTRY_DSN to ship them to Sentry."
        )
        return status()

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        sentry_sdk.init(
            dsn=dsn,
            release=release,
            environment=os.environ.get("SENTRY_ENVIRONMENT", "development"),
            # Sampled, not exhaustive: a full-fidelity trace of an 85-call agent run
            # is expensive and rarely more informative than a representative sample.
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
            # Contract text is confidential. Never let the SDK attach request
            # bodies, headers or cookies automatically.
            send_default_pii=False,
            max_request_body_size="never",
            before_send=_before_send,
            integrations=[
                FastApiIntegration(),
                SqlalchemyIntegration(),
                LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
            ],
        )
        _sentry = sentry_sdk
        logger.info("Sentry error monitoring enabled.")
    except ImportError:
        logger.warning(
            "SENTRY_DSN is set but sentry-sdk is not installed. "
            "Install it with: pip install 'sentry-sdk[fastapi]'. "
            "Falling back to structured logging."
        )
    except Exception as exc:
        logger.warning("Sentry init failed (%s); using structured logging.", exc)

    return status()


def _before_send(event: Dict[str, Any], _hint: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Last line of defence: scrub every event on its way out."""
    try:
        return scrub(event)
    except Exception:
        # If scrubbing fails we drop the event rather than risk shipping a secret.
        return None


def capture_exception(
    exc: BaseException,
    *,
    context: Optional[Dict[str, Any]] = None,
    agent: Optional[str] = None,
    contract_id: Optional[str] = None,
    clause_id: Optional[str] = None,
) -> None:
    """Report an exception. Never raises.

    `agent` / `contract_id` / `clause_id` are attached as tags so a failure can be
    traced to the specific agent and clause that produced it.
    """
    tags = {
        k: v
        for k, v in {
            "agent": agent,
            "contract_id": contract_id,
            "clause_id": clause_id,
        }.items()
        if v
    }
    safe_context = scrub(context or {})

    try:
        if _sentry is not None:
            with _sentry.push_scope() as scope:
                for key, value in tags.items():
                    scope.set_tag(key, value)
                if safe_context:
                    scope.set_context("dharma", safe_context)
                _sentry.capture_exception(exc)
        else:
            logger.error(
                json.dumps(
                    {
                        "event": "unhandled_exception",
                        "timestamp": time.time(),
                        "error_type": type(exc).__name__,
                        "error": scrub(str(exc)),
                        "traceback": scrub(
                            "".join(
                                traceback.format_exception(type(exc), exc, exc.__traceback__)
                            )[-4000:]
                        ),
                        **tags,
                        "context": safe_context,
                    },
                    default=str,
                )
            )
    except Exception:
        # Monitoring must never take down the request it is monitoring.
        logger.exception("Error reporting itself failed")


def capture_message(message: str, level: str = "warning", **tags: Any) -> None:
    """Report a noteworthy non-exception event. Never raises."""
    try:
        if _sentry is not None:
            with _sentry.push_scope() as scope:
                for key, value in tags.items():
                    if value:
                        scope.set_tag(key, str(value))
                _sentry.capture_message(scrub(message), level=level)
        else:
            logger.warning(
                json.dumps(
                    {"event": "message", "level": level, "message": scrub(message), **tags},
                    default=str,
                )
            )
    except Exception:
        logger.exception("Error reporting itself failed")


def status() -> Dict[str, Any]:
    """Reported by `/api/health` so the active sink is never a guess."""
    return {
        "sink": "sentry" if _sentry is not None else "structured-logs",
        "sentry_enabled": _sentry is not None,
        "dsn_configured": bool((os.environ.get("SENTRY_DSN") or "").strip()),
        "environment": os.environ.get("SENTRY_ENVIRONMENT", "development"),
        "scrubbing": "secrets redacted from every event before it leaves the process",
    }
