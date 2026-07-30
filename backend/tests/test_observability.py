"""
Tests for the error-monitoring layer.

The scrubber is the part worth testing hardest: an error reporter that ships an
API key to a third party is worse than having no reporter at all. These assert
that secrets never survive `scrub()`, in every shape they realistically appear —
nested dicts, connection URIs, tracebacks, and key-like field names.
"""

from __future__ import annotations

from app.observability import capture_exception, capture_message, scrub, status


# ─────────────────────────────────────────────────────────────────────────────
# Scrubbing
# ─────────────────────────────────────────────────────────────────────────────


def test_openai_key_is_redacted_from_strings() -> None:
    text = "Request failed with key sk-proj-AbCdEf0123456789XyZaBcDeFgHi"
    result = scrub(text)
    assert "sk-proj-AbCdEf0123456789" not in result
    assert "REDACTED" in result


def test_jwt_is_redacted() -> None:
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NSJ9.abcDEF123_-xyz"
    result = scrub(f"Authorization failed for {token}")
    assert token not in result
    assert "***JWT***" in result


def test_credentials_in_a_connection_uri_are_redacted() -> None:
    result = scrub("postgresql://dharma:sup3rs3cret@db.example.com:5432/dharma")
    assert "sup3rs3cret" not in result
    assert "***:***@" in result
    # The host is diagnostically useful and is not a secret.
    assert "db.example.com" in result


def test_secret_named_keys_are_redacted_regardless_of_value() -> None:
    payload = {
        "api_key": "anything-at-all",
        "Authorization": "Bearer abc",
        "password": "hunter2",
        "DATABASE_PASSWORD": "x",
        "contract_id": "keep-me",
    }
    result = scrub(payload)
    assert result["api_key"] == "***REDACTED***"
    assert result["Authorization"] == "***REDACTED***"
    assert result["password"] == "***REDACTED***"
    assert result["DATABASE_PASSWORD"] == "***REDACTED***"
    # Non-secret context must survive, or reports become useless.
    assert result["contract_id"] == "keep-me"


def test_scrubbing_recurses_through_nested_structures() -> None:
    payload = {
        "request": {
            "headers": [{"authorization": "Bearer secret"}],
            "body": {"nested": {"token": "abc123"}},
        },
        "message": "failed with sk-proj-ZZZZZZZZZZZZZZZZZZZZ",
    }
    result = scrub(payload)
    assert result["request"]["headers"][0]["authorization"] == "***REDACTED***"
    assert result["request"]["body"]["nested"]["token"] == "***REDACTED***"
    assert "sk-proj-ZZZZ" not in result["message"]


def test_scrubbing_preserves_non_secret_types() -> None:
    payload = {"count": 17, "score": 83.5, "escalated": True, "items": None}
    assert scrub(payload) == payload


# ─────────────────────────────────────────────────────────────────────────────
# Reporting must never raise
# ─────────────────────────────────────────────────────────────────────────────


def test_capture_exception_never_raises() -> None:
    """A monitoring failure must not become an application failure."""
    try:
        raise ValueError("boom sk-proj-AAAAAAAAAAAAAAAAAAAA")
    except ValueError as exc:
        # Must return normally even with unserialisable context.
        capture_exception(
            exc,
            context={"weird": object(), "contract_id": "c1"},
            agent="Risk Assessment Agent",
            clause_id="cl1",
        )


def test_capture_message_never_raises() -> None:
    capture_message("something odd happened", level="warning", agent="x")


def test_status_reports_the_active_sink() -> None:
    report = status()
    assert report["sink"] in ("sentry", "structured-logs")
    assert "scrubbing" in report
    # Without a DSN configured in tests, it must be the logging fallback.
    assert report["sentry_enabled"] is False
