"""
Unit tests for risk scoring.

Covers the four things that must hold for risk output to be trustworthy:

  1. **Bounds and monotonicity** — scores stay in 0–100, and a worse clause always
     scores higher than a safer one of the same category.
  2. **Playbook rule evaluation** — every `rule_type` fires when it should and,
     just as importantly, does not fire when it shouldn't.
  3. **Level thresholds** — the score→level mapping is exact at boundaries.
  4. **Contract rollup** — category weighting and the severity-concentration
     penalty behave as designed, and the penalty cannot manufacture a rating on
     its own.
"""

from __future__ import annotations

import pytest

from app.agents.heuristics import (
    aggregate_contract_risk,
    evaluate_playbook_rules,
    score_clause_heuristic,
)
from app.domain import ClauseCategory, RiskLevel, category_weight, risk_level_for_score

UNCAPPED_LIABILITY = (
    "8. Limitation of Liability. Customer shall have unlimited liability for any "
    "breach of this Agreement, including consequential damages."
)
CAPPED_LIABILITY = (
    "8. Limitation of Liability. Each party's aggregate liability shall be capped "
    "at the fees paid in the preceding twelve (12) months, and neither party shall "
    "be liable for consequential damages."
)

LIABILITY_CAP_RULE = {
    "id": "PB-LIAB-001",
    "title": "Liability exposure above $100,000 is High Risk",
    "category": ClauseCategory.LIABILITY.value,
    "rule_type": "monetary_threshold",
    "operator": "gt",
    "threshold": 100_000,
    "risk_points": 30,
    "severity": "High",
}


# ─────────────────────────────────────────────────────────────────────────────
# Bounds and ordering
# ─────────────────────────────────────────────────────────────────────────────


def test_score_is_within_bounds() -> None:
    for text in (UNCAPPED_LIABILITY, CAPPED_LIABILITY, "", "Short clause."):
        result = score_clause_heuristic(text, ClauseCategory.LIABILITY.value)
        assert 0.0 <= result.score <= 100.0


def test_uncapped_liability_scores_higher_than_capped() -> None:
    uncapped = score_clause_heuristic(UNCAPPED_LIABILITY, ClauseCategory.LIABILITY.value)
    capped = score_clause_heuristic(CAPPED_LIABILITY, ClauseCategory.LIABILITY.value)
    assert uncapped.score > capped.score


def test_mitigating_language_reduces_score() -> None:
    harsh = score_clause_heuristic(
        "Supplier may terminate this Agreement without prior written notice.",
        ClauseCategory.TERMINATION.value,
    )
    softened = score_clause_heuristic(
        "Either party may terminate for cause upon thirty (30) days' prior written "
        "notice, and each party shall have a cure period.",
        ClauseCategory.TERMINATION.value,
    )
    assert softened.score < harsh.score


def test_empty_clause_scores_zero_and_low() -> None:
    result = score_clause_heuristic("", ClauseCategory.LIABILITY.value)
    assert result.score == 0.0
    assert result.level == RiskLevel.LOW.value


def test_score_is_deterministic() -> None:
    """The Risk Simulator recomputes on every keystroke; identical input must
    always give an identical score."""
    first = score_clause_heuristic(UNCAPPED_LIABILITY, ClauseCategory.LIABILITY.value)
    second = score_clause_heuristic(UNCAPPED_LIABILITY, ClauseCategory.LIABILITY.value)
    assert first.score == second.score
    assert first.level == second.level


def test_boilerplate_category_scores_lower_than_liability() -> None:
    """A definitions clause must not score like an indemnity — this was a real
    bug when a wildcard rule fired on every clause."""
    definitions = score_clause_heuristic(
        "1. Definitions. Capitalised terms shall mean as set out in Schedule A.",
        ClauseCategory.DEFINITIONS.value,
    )
    liability = score_clause_heuristic(UNCAPPED_LIABILITY, ClauseCategory.LIABILITY.value)
    assert definitions.score < liability.score
    assert definitions.level == RiskLevel.LOW.value


def test_rationale_is_populated() -> None:
    result = score_clause_heuristic(UNCAPPED_LIABILITY, ClauseCategory.LIABILITY.value)
    assert result.rationale
    assert ClauseCategory.LIABILITY.value in result.rationale


# ─────────────────────────────────────────────────────────────────────────────
# Playbook rules — the brief's own example: liability > $100K → High Risk
# ─────────────────────────────────────────────────────────────────────────────


def test_monetary_threshold_rule_fires_above_threshold() -> None:
    findings = evaluate_playbook_rules(
        "Aggregate liability shall not exceed $250,000 per claim.",
        ClauseCategory.LIABILITY.value,
        [LIABILITY_CAP_RULE],
    )
    assert len(findings) == 1
    assert findings[0].rule_id == "PB-LIAB-001"
    assert findings[0].points == 30


def test_monetary_threshold_rule_does_not_fire_below_threshold() -> None:
    findings = evaluate_playbook_rules(
        "Aggregate liability shall not exceed $50,000 per claim.",
        ClauseCategory.LIABILITY.value,
        [LIABILITY_CAP_RULE],
    )
    assert findings == []


def test_liability_above_100k_is_high_risk_end_to_end() -> None:
    """The brief's worked example, through the full scoring path."""
    result = score_clause_heuristic(
        "8. Limitation of Liability. Supplier's aggregate liability shall not exceed "
        "$150,000 in any circumstances.",
        ClauseCategory.LIABILITY.value,
        [LIABILITY_CAP_RULE],
    )
    assert "PB-LIAB-001" in result.triggered_rule_ids
    assert result.level in (RiskLevel.HIGH.value, RiskLevel.CRITICAL.value)


def test_rule_scoped_to_another_category_does_not_fire() -> None:
    """A Liability-scoped rule must not fire on a Payment clause."""
    findings = evaluate_playbook_rules(
        "Customer shall pay $500,000 in annual fees.",
        ClauseCategory.PAYMENT.value,
        [LIABILITY_CAP_RULE],
    )
    assert findings == []


def test_forbidden_language_rule_fires_on_match() -> None:
    rule = {
        "id": "PB-LIAB-002",
        "title": "Uncapped liability prohibited",
        "category": ClauseCategory.LIABILITY.value,
        "rule_type": "forbidden_language",
        "keywords": ["unlimited liability", "no cap on liability"],
        "risk_points": 40,
    }
    findings = evaluate_playbook_rules(
        UNCAPPED_LIABILITY, ClauseCategory.LIABILITY.value, [rule]
    )
    assert len(findings) == 1
    assert findings[0].points == 40


def test_forbidden_language_rule_silent_when_absent() -> None:
    rule = {
        "id": "PB-LIAB-002",
        "category": ClauseCategory.LIABILITY.value,
        "rule_type": "forbidden_language",
        "keywords": ["unlimited liability"],
        "risk_points": 40,
    }
    findings = evaluate_playbook_rules(
        CAPPED_LIABILITY, ClauseCategory.LIABILITY.value, [rule]
    )
    assert findings == []


def test_required_language_rule_fires_when_language_missing() -> None:
    rule = {
        "id": "PB-TERM-001",
        "title": "Notice required",
        "category": ClauseCategory.TERMINATION.value,
        "rule_type": "required_language",
        "keywords": ["written notice", "cure period"],
        "risk_points": 25,
    }
    findings = evaluate_playbook_rules(
        "Supplier may terminate this Agreement immediately at its sole discretion.",
        ClauseCategory.TERMINATION.value,
        [rule],
    )
    assert len(findings) == 1
    assert "missing required language" in findings[0].detail


def test_required_language_rule_silent_when_language_present() -> None:
    rule = {
        "id": "PB-TERM-001",
        "category": ClauseCategory.TERMINATION.value,
        "rule_type": "required_language",
        "keywords": ["written notice"],
        "risk_points": 25,
    }
    findings = evaluate_playbook_rules(
        "Either party may terminate upon thirty (30) days' prior written notice.",
        ClauseCategory.TERMINATION.value,
        [rule],
    )
    assert findings == []


def test_wildcard_required_language_rule_is_ignored() -> None:
    """Regression: a globally-scoped required-language rule fired on every
    unrelated clause and pinned the whole contract to High risk."""
    rule = {
        "id": "PB-BAD-001",
        "title": "Governing law must name a jurisdiction",
        "category": "*",
        "rule_type": "required_language",
        "keywords": ["delaware", "new york"],
        "risk_points": 10,
    }
    findings = evaluate_playbook_rules(
        "3. Payment Terms. Customer shall pay all invoices Net 30.",
        ClauseCategory.PAYMENT.value,
        [rule],
    )
    assert findings == []


def test_wildcard_forbidden_language_rule_still_applies_everywhere() -> None:
    """Global prohibitions are legitimate and must keep working."""
    rule = {
        "id": "PB-GLOBAL-001",
        "title": "No unilateral amendment",
        "category": "*",
        "rule_type": "forbidden_language",
        "keywords": ["unilaterally amend"],
        "risk_points": 28,
    }
    findings = evaluate_playbook_rules(
        "14. Amendment. Supplier may unilaterally amend these terms at any time.",
        ClauseCategory.OTHER.value,
        [rule],
    )
    assert len(findings) == 1


def test_duration_threshold_rule_fires() -> None:
    rule = {
        "id": "PB-TERM-002",
        "title": "Notice longer than 180 days is excessive",
        "category": ClauseCategory.TERMINATION.value,
        "rule_type": "duration_threshold",
        "operator": "gt",
        "threshold": 180,
        "risk_points": 15,
    }
    findings = evaluate_playbook_rules(
        "Either party must give 240 days written notice of non-renewal.",
        ClauseCategory.TERMINATION.value,
        [rule],
    )
    assert len(findings) == 1
    assert "240 days" in findings[0].detail


@pytest.mark.parametrize(
    "operator,observed_text,should_fire",
    [
        ("gt", "$150,000", True),
        ("gt", "$100,000", False),
        ("gte", "$100,000", True),
        ("lt", "$50,000", True),
        ("lt", "$150,000", False),
        ("lte", "$100,000", True),
        ("eq", "$100,000", True),
        ("eq", "$100,001", False),
    ],
)
def test_comparison_operators(operator: str, observed_text: str, should_fire: bool) -> None:
    rule = {**LIABILITY_CAP_RULE, "operator": operator}
    findings = evaluate_playbook_rules(
        f"Aggregate liability shall not exceed {observed_text}.",
        ClauseCategory.LIABILITY.value,
        [rule],
    )
    assert bool(findings) is should_fire


def test_multiple_rules_accumulate_points() -> None:
    rules = [
        LIABILITY_CAP_RULE,
        {
            "id": "PB-LIAB-002",
            "category": ClauseCategory.LIABILITY.value,
            "rule_type": "forbidden_language",
            "keywords": ["unlimited liability"],
            "risk_points": 40,
        },
    ]
    findings = evaluate_playbook_rules(
        "Customer shall have unlimited liability up to $250,000 and beyond.",
        ClauseCategory.LIABILITY.value,
        rules,
    )
    assert len(findings) == 2
    assert sum(f.points for f in findings) == 70


def test_no_rules_yields_no_playbook_findings() -> None:
    result = score_clause_heuristic(UNCAPPED_LIABILITY, ClauseCategory.LIABILITY.value, [])
    assert result.triggered_rule_ids == []
    assert all(f.source != "playbook" for f in result.findings)


# ─────────────────────────────────────────────────────────────────────────────
# Level thresholds
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "score,expected",
    [
        (0, RiskLevel.LOW),
        (39.9, RiskLevel.LOW),
        (40, RiskLevel.MEDIUM),
        (69.9, RiskLevel.MEDIUM),
        (70, RiskLevel.HIGH),
        (89.9, RiskLevel.HIGH),
        (90, RiskLevel.CRITICAL),
        (100, RiskLevel.CRITICAL),
    ],
)
def test_risk_level_boundaries(score: float, expected: RiskLevel) -> None:
    assert risk_level_for_score(score) == expected


def test_custom_thresholds_are_respected() -> None:
    assert risk_level_for_score(55, high_threshold=50, medium_threshold=25) == RiskLevel.HIGH
    assert risk_level_for_score(30, high_threshold=50, medium_threshold=25) == RiskLevel.MEDIUM


# ─────────────────────────────────────────────────────────────────────────────
# Contract rollup
# ─────────────────────────────────────────────────────────────────────────────


def test_empty_rollup_is_zero_and_low() -> None:
    result = aggregate_contract_risk([])
    assert result["score"] == 0.0
    assert result["level"] == RiskLevel.LOW.value
    assert result["clause_count"] == 0


def test_rollup_counts_distribution() -> None:
    result = aggregate_contract_risk(
        [
            {"category": ClauseCategory.PAYMENT.value, "score": 20, "level": "Low"},
            {"category": ClauseCategory.LIABILITY.value, "score": 75, "level": "High"},
            {"category": ClauseCategory.IP.value, "score": 95, "level": "Critical"},
        ]
    )
    assert result["clause_count"] == 3
    assert result["distribution"]["Low"] == 1
    assert result["distribution"]["High"] == 1
    assert result["distribution"]["Critical"] == 1


def test_rollup_weights_liability_above_definitions() -> None:
    """Category weighting must matter: the same score in a Liability clause should
    pull the contract score higher than in a Definitions clause."""
    liability_heavy = aggregate_contract_risk(
        [
            {"category": ClauseCategory.LIABILITY.value, "score": 80, "level": "High"},
            {"category": ClauseCategory.DEFINITIONS.value, "score": 10, "level": "Low"},
        ]
    )
    definitions_heavy = aggregate_contract_risk(
        [
            {"category": ClauseCategory.DEFINITIONS.value, "score": 80, "level": "High"},
            {"category": ClauseCategory.LIABILITY.value, "score": 10, "level": "Low"},
        ]
    )
    assert liability_heavy["score"] > definitions_heavy["score"]


def test_liability_weight_exceeds_definitions_weight() -> None:
    assert category_weight(ClauseCategory.LIABILITY.value) > category_weight(
        ClauseCategory.DEFINITIONS.value
    )


def test_unknown_category_uses_default_weight() -> None:
    assert category_weight("Not A Real Category") == 1.0


def test_severity_concentration_penalty_applies() -> None:
    """Benign clauses must not average away a deal-breaking one."""
    all_severe = aggregate_contract_risk(
        [{"category": ClauseCategory.LIABILITY.value, "score": 75, "level": "High"}] * 4
    )
    assert all_severe["severity_penalty"] > 0
    assert all_severe["score"] > all_severe["weighted_mean"]


def test_severity_penalty_is_capped() -> None:
    result = aggregate_contract_risk(
        [{"category": ClauseCategory.LIABILITY.value, "score": 95, "level": "Critical"}] * 20
    )
    assert result["severity_penalty"] <= 18.0


def test_penalty_alone_cannot_create_a_critical_rating() -> None:
    """All-Low clauses must never roll up to High/Critical via the penalty."""
    result = aggregate_contract_risk(
        [{"category": ClauseCategory.PAYMENT.value, "score": 15, "level": "Low"}] * 10
    )
    assert result["level"] == RiskLevel.LOW.value


def test_rollup_score_stays_within_bounds() -> None:
    result = aggregate_contract_risk(
        [{"category": ClauseCategory.LIABILITY.value, "score": 100, "level": "Critical"}] * 30
    )
    assert 0.0 <= result["score"] <= 100.0


# ─────────────────────────────────────────────────────────────────────────────
# Agent-level contract
# ─────────────────────────────────────────────────────────────────────────────


def test_agent_falls_back_to_heuristic_when_model_fails(monkeypatch) -> None:
    from app.agents.contract_agents import RiskAssessmentAgent

    agent = RiskAssessmentAgent()
    monkeypatch.setattr(agent, "run_json", lambda *a, **k: None)
    result = agent.assess(UNCAPPED_LIABILITY, ClauseCategory.LIABILITY.value, [])
    assert result["method"] == "heuristic-fallback"
    assert 0 <= result["risk_score"] <= 100
    assert result["suggested_fix"]


def test_agent_clamps_absurd_model_score(monkeypatch) -> None:
    from app.agents.contract_agents import RiskAssessmentAgent

    agent = RiskAssessmentAgent()
    monkeypatch.setattr(
        agent,
        "run_json",
        lambda *a, **k: {"risk_score": 9999, "risk_level": "Nonsense", "confidence": 0.9},
    )
    result = agent.assess(UNCAPPED_LIABILITY, ClauseCategory.LIABILITY.value, [])
    assert 0 <= result["risk_score"] <= 100
    assert result["risk_level"] in [level.value for level in RiskLevel]


def test_fired_playbook_rule_sets_a_high_risk_floor(monkeypatch) -> None:
    """Policy is not negotiable by model opinion: if a rule fires, the clause
    cannot be scored below the High threshold."""
    from app.agents.contract_agents import RiskAssessmentAgent
    from app.config import settings

    agent = RiskAssessmentAgent()
    monkeypatch.setattr(
        agent,
        "run_json",
        lambda *a, **k: {"risk_score": 5, "risk_level": "Low", "confidence": 0.95},
    )
    result = agent.assess(
        "Aggregate liability shall not exceed $250,000.",
        ClauseCategory.LIABILITY.value,
        [LIABILITY_CAP_RULE],
    )
    assert result["risk_score"] >= settings.risk_high_threshold


# ─────────────────────────────────────────────────────────────────────────────
# Database URL handling (regression — schema ownership)
# ─────────────────────────────────────────────────────────────────────────────


def test_sqlalchemy_url_strips_the_prisma_schema_parameter() -> None:
    """The backend must ignore `?schema=auth` and stay on `public`.

    Prisma and SQLAlchemy share one Postgres database but own different schemas.
    The frontend's DATABASE_URL carries `?schema=auth` to confine `prisma db push`
    to its own tables — without that scope it treats the backend's `dharma_*`
    tables as drift and drops them:

        "You are about to drop the `dharma_playbook_rules` table, which is not
         empty (14 rows)."

    Because the same base URL is shared by both services, the backend stripping
    that query string is what makes one variable safe for both. If this ever
    stopped stripping, the backend would silently start reading and writing the
    auth schema instead.
    """
    from app.config import Settings

    settings = Settings(
        DATABASE_URL="postgresql://dharma:dharma@localhost:5432/dharma?schema=auth"
    )
    assert "schema=auth" not in settings.sqlalchemy_url
    assert settings.sqlalchemy_url == (
        "postgresql+psycopg://dharma:dharma@localhost:5432/dharma"
    )


def test_sqlalchemy_url_normalises_the_postgres_scheme() -> None:
    from app.config import Settings

    settings = Settings(DATABASE_URL="postgres://u:p@host:5432/db")
    assert settings.sqlalchemy_url.startswith("postgresql+psycopg://")
