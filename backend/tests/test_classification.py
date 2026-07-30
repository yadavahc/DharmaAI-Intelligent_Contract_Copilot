"""
Unit tests for clause classification.

These target `agents/heuristics.classify_clause_heuristic` — the deterministic
classifier. That is deliberate: it is the function whose behaviour we can assert
on, it backs the LLM path as a fallback, and it decides confidence, which drives
the hallucination guardrail. Asserting on live model prose would test OpenAI, not
Dharma AI.

`ClauseClassificationAgent` is also tested for the contract it guarantees
regardless of what the model returns (in-taxonomy category, clamped confidence,
damped confidence on model/heuristic disagreement).
"""

from __future__ import annotations

import pytest

from app.agents.heuristics import (
    classify_clause_heuristic,
    extract_durations_days,
    extract_money,
    max_money,
)
from app.domain import ClauseCategory
from app.services.clauses import split_into_clauses


# ─────────────────────────────────────────────────────────────────────────────
# Category detection
# ─────────────────────────────────────────────────────────────────────────────

CLAUSE_FIXTURES = [
    (
        "8. Limitation of Liability. In no event shall either party's aggregate "
        "liability exceed the fees paid in the preceding twelve months, and neither "
        "party shall be liable for consequential damages.",
        ClauseCategory.LIABILITY.value,
    ),
    (
        "3. Payment Terms. Customer shall pay all invoices Net 30 from the date of "
        "receipt of a valid invoice. Late payments accrue interest at 1% per month.",
        ClauseCategory.PAYMENT.value,
    ),
    (
        "5. Termination. Either party may terminate this Agreement for material "
        "breach upon thirty (30) days' prior written notice and a fifteen (15) day "
        "cure period.",
        ClauseCategory.TERMINATION.value,
    ),
    (
        "6. Confidentiality. Each party shall hold the other party's Confidential "
        "Information and proprietary information in strict confidence and shall not "
        "disclose it under this non-disclosure obligation.",
        ClauseCategory.CONFIDENTIALITY.value,
    ),
    (
        "7. Intellectual Property. Supplier assigns all right, title, and interest "
        "in the work product, including any copyright and patent rights, and grants "
        "a licence to any derivative works.",
        ClauseCategory.IP.value,
    ),
    (
        "9. Indemnification. Customer shall defend, indemnify and hold harmless "
        "Supplier against any third-party claim arising under this Agreement.",
        ClauseCategory.INDEMNIFICATION.value,
    ),
    (
        "10. Data Protection. Supplier shall process personal data in accordance "
        "with GDPR and the data processing agreement, and shall notify Customer of "
        "any data breach affecting a data subject.",
        ClauseCategory.DATA_PRIVACY.value,
    ),
    (
        "11. Warranties. The services are provided AS IS and Supplier disclaims all "
        "warranties, including any implied warranty of merchantability or fitness "
        "for a particular purpose.",
        ClauseCategory.WARRANTY.value,
    ),
    (
        "4. Term and Renewal. This Agreement shall automatically renew for "
        "successive twelve (12) month terms unless either party gives notice of "
        "non-renewal.",
        ClauseCategory.RENEWAL.value,
    ),
    (
        "15. Governing Law. This Agreement shall be governed by the laws of the "
        "State of Delaware, and the parties submit to the exclusive jurisdiction and "
        "venue of its courts.",
        ClauseCategory.GOVERNING_LAW.value,
    ),
    (
        "16. Dispute Resolution. All disputes shall be resolved by binding "
        "arbitration before a single arbitrator, and each party waives any right to "
        "a jury trial or class action.",
        ClauseCategory.DISPUTE_RESOLUTION.value,
    ),
    (
        "12. Insurance. Supplier shall maintain commercial general liability "
        "insurance coverage of not less than $1,000,000 and provide a certificate of "
        "insurance from its insurer.",
        ClauseCategory.INSURANCE.value,
    ),
    (
        "17. Service Levels. Supplier shall maintain 99.9% uptime availability. "
        "Failure to meet the response time entitles Customer to a service credit for "
        "any downtime.",
        ClauseCategory.SLA.value,
    ),
    (
        "13. Force Majeure. Neither party shall be liable for any delay caused by "
        "acts of god, epidemic or pandemic, or other events beyond the reasonable "
        "control of that party.",
        ClauseCategory.FORCE_MAJEURE.value,
    ),
]


@pytest.mark.parametrize("text,expected", CLAUSE_FIXTURES)
def test_classifies_clause_into_expected_category(text: str, expected: str) -> None:
    result = classify_clause_heuristic(text)
    assert result.category == expected, (
        f"expected {expected}, got {result.category} "
        f"(signals: {result.signals}, alternatives: {result.alternatives})"
    )


@pytest.mark.parametrize("text,expected", CLAUSE_FIXTURES)
def test_category_is_always_in_taxonomy(text: str, expected: str) -> None:
    assert classify_clause_heuristic(text).category in ClauseCategory.values()


def test_heading_outweighs_incidental_keywords() -> None:
    """A clause titled 'Limitation of Liability' is a Liability clause even when
    it mentions payment terms in passing."""
    text = (
        "12.1 Limitation of Liability. Notwithstanding any provision regarding "
        "payment or invoice terms, Supplier's total liability shall be capped."
    )
    assert classify_clause_heuristic(text).category == ClauseCategory.LIABILITY.value


def test_multi_word_phrases_beat_single_words() -> None:
    """'limitation of liability' should outrank a lone 'payment' mention."""
    result = classify_clause_heuristic(
        "This limitation of liability provision survives any payment dispute."
    )
    assert result.category == ClauseCategory.LIABILITY.value


# ─────────────────────────────────────────────────────────────────────────────
# Confidence calibration
# ─────────────────────────────────────────────────────────────────────────────


def test_confidence_is_bounded() -> None:
    for text, _ in CLAUSE_FIXTURES:
        confidence = classify_clause_heuristic(text).confidence
        assert 0.0 <= confidence <= 1.0


def test_unambiguous_clause_scores_high_confidence() -> None:
    result = classify_clause_heuristic(
        "8. Limitation of Liability. Supplier's aggregate liability under this "
        "limitation of liability clause shall not exceed the cap on liability set "
        "out herein, excluding consequential damages."
    )
    assert result.category == ClauseCategory.LIABILITY.value
    assert result.confidence >= 0.8


def test_ambiguous_clause_scores_lower_confidence_than_unambiguous() -> None:
    """Confidence must be comparative, not a constant — the hallucination
    guardrail depends on a genuinely low score for ambiguous input."""
    clear = classify_clause_heuristic(
        "Limitation of Liability. Aggregate liability is capped and consequential "
        "damages are excluded under this limitation of liability provision."
    )
    ambiguous = classify_clause_heuristic(
        "The parties acknowledge the matters set out above and agree to proceed "
        "in accordance with the terms of this document."
    )
    assert ambiguous.confidence < clear.confidence


def test_empty_clause_returns_other_with_zero_confidence() -> None:
    result = classify_clause_heuristic("   \n  ")
    assert result.category == ClauseCategory.OTHER.value
    assert result.confidence == 0.0


def test_unmatched_text_falls_back_to_other() -> None:
    result = classify_clause_heuristic("Zxqv mnbtr plkjh gfdsa qwerty uiop.")
    assert result.category == ClauseCategory.OTHER.value
    assert result.confidence < 0.5


def test_alternatives_exclude_the_winner() -> None:
    result = classify_clause_heuristic(
        "Payment of all invoices Net 90 shall not limit Supplier's liability for "
        "consequential damages under this agreement."
    )
    assert result.category not in [a["category"] for a in result.alternatives]


# ─────────────────────────────────────────────────────────────────────────────
# Value extraction (feeds the monetary/duration playbook rules)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text,expected",
    [
        ("liability capped at $100,000 per claim", 100_000.0),
        ("fees of $1.5 million per annum", 1_500_000.0),
        ("a cap of $2M applies", 2_000_000.0),
        ("USD 250,000 in aggregate", 250_000.0),
        ("50,000 dollars payable on signature", 50_000.0),
        ("total of $480,000 per annum", 480_000.0),
        ("$2.5k administrative fee", 2_500.0),
    ],
)
def test_extract_money_normalises_amounts(text: str, expected: float) -> None:
    assert max_money(text) == pytest.approx(expected)


def test_extract_money_returns_all_amounts() -> None:
    amounts = extract_money("fees of $10,000 rising to $25,000 with a $1M cap")
    assert 10_000.0 in amounts
    assert 25_000.0 in amounts
    assert 1_000_000.0 in amounts


def test_no_money_returns_none() -> None:
    assert max_money("no monetary amounts appear in this clause") is None


@pytest.mark.parametrize(
    "text,expected_days",
    [
        ("thirty (30) days' written notice", 30),
        ("a period of 12 months", 360),
        ("two (2) years from the Effective Date", 730),
        ("within 6 weeks of the request", 42),
        ("ninety days prior notice", 90),
    ],
)
def test_extract_durations_in_days(text: str, expected_days: int) -> None:
    assert expected_days in extract_durations_days(text)


def test_parenthesised_digits_win_over_spelled_word() -> None:
    """'thirty (30) days' must yield 30 once, not both 30 and a word-parse."""
    assert extract_durations_days("thirty (30) days") == [30]


# ─────────────────────────────────────────────────────────────────────────────
# Clause splitting — classification operates on whatever this produces
# ─────────────────────────────────────────────────────────────────────────────


def test_splits_numbered_contract_into_clauses() -> None:
    text = (
        "1. Definitions. Capitalised terms have the meanings given in Schedule A "
        "and any exhibits attached to this Agreement for all purposes herein.\n\n"
        "2. Payment Terms. Customer shall pay all invoices Net 30 from receipt of "
        "a valid invoice issued by Supplier under this Agreement.\n\n"
        "3. Limitation of Liability. Aggregate liability shall not exceed the fees "
        "paid in the twelve months preceding the claim giving rise to liability.\n"
    )
    clauses = split_into_clauses(text)
    assert len(clauses) == 3
    assert [c.label for c in clauses] == ["1", "2", "3"]
    assert clauses[2].heading == "Limitation of Liability"


def test_labelled_clause_is_never_merged_away_for_being_short() -> None:
    """A short but explicitly numbered clause is real structure, not a fragment."""
    text = (
        "1. Definitions. Terms have their given meanings.\n\n"
        "2. Payment. Customer shall pay all invoices within thirty days of receipt "
        "of a valid invoice from Supplier in accordance with this Agreement.\n\n"
        "3. Liability. Aggregate liability is capped at the fees paid in the "
        "preceding twelve month period under this Agreement.\n"
    )
    labels = [c.label for c in split_into_clauses(text)]
    assert "1" in labels, f"short labelled clause was merged away: {labels}"


def test_oversized_clause_is_split_at_sentence_boundaries() -> None:
    sentence = (
        "Supplier shall provide the services in accordance with the applicable "
        "statement of work and all relevant specifications. "
    )
    text = "1. Services. " + (sentence * 60)
    clauses = split_into_clauses(text)
    assert len(clauses) > 1
    assert all(len(c.text) <= 4000 for c in clauses)


def test_split_always_produces_at_least_one_clause_for_real_text() -> None:
    clauses = split_into_clauses(
        "This agreement is made between the parties on the date set out above and "
        "shall be binding upon their successors and permitted assigns."
    )
    assert len(clauses) >= 1


def test_empty_document_yields_no_clauses() -> None:
    assert split_into_clauses("") == []
    assert split_into_clauses("   \n\n  ") == []


# ─────────────────────────────────────────────────────────────────────────────
# Agent-level contract (holds regardless of what the LLM returns)
# ─────────────────────────────────────────────────────────────────────────────


def test_agent_rejects_out_of_taxonomy_category_from_model(monkeypatch) -> None:
    from app.agents.contract_agents import ClauseClassificationAgent

    agent = ClauseClassificationAgent()
    monkeypatch.setattr(
        agent,
        "run_json",
        lambda *a, **k: {"category": "Completely Made Up", "confidence": 0.99},
    )
    result = agent.classify(
        "8. Limitation of Liability. Aggregate liability shall be capped."
    )
    assert result["category"] in ClauseCategory.values()
    assert result["category"] == ClauseCategory.LIABILITY.value


def test_agent_clamps_out_of_range_confidence(monkeypatch) -> None:
    from app.agents.contract_agents import ClauseClassificationAgent

    agent = ClauseClassificationAgent()
    monkeypatch.setattr(
        agent,
        "run_json",
        lambda *a, **k: {"category": ClauseCategory.LIABILITY.value, "confidence": 42},
    )
    result = agent.classify("Limitation of Liability. Liability is capped.")
    assert 0.0 <= result["confidence"] <= 1.0


def test_agent_damps_confidence_when_model_contradicts_heuristic(monkeypatch) -> None:
    """Disagreement is evidence of ambiguity and must lower confidence, so the
    hallucination guardrail can surface it."""
    from app.agents.contract_agents import ClauseClassificationAgent

    agent = ClauseClassificationAgent()
    monkeypatch.setattr(
        agent,
        "run_json",
        lambda *a, **k: {"category": ClauseCategory.INSURANCE.value, "confidence": 0.98},
    )
    result = agent.classify(
        "8. Limitation of Liability. Supplier's aggregate liability under this "
        "limitation of liability clause shall not exceed the stated cap on "
        "liability, excluding consequential damages."
    )
    assert result["confidence"] <= 0.62


def test_agent_falls_back_to_heuristic_when_model_returns_nothing(monkeypatch) -> None:
    from app.agents.contract_agents import ClauseClassificationAgent

    agent = ClauseClassificationAgent()
    monkeypatch.setattr(agent, "run_json", lambda *a, **k: None)
    result = agent.classify(
        "3. Payment Terms. Customer shall pay all invoices Net 30 from receipt."
    )
    assert result["category"] == ClauseCategory.PAYMENT.value
    assert result["method"] == "heuristic-fallback"


# ─────────────────────────────────────────────────────────────────────────────
# JSON-mode contract (regression)
# ─────────────────────────────────────────────────────────────────────────────


def test_json_mode_agents_always_mention_json_in_instructions() -> None:
    """OpenAI rejects `response_format={"type":"json_object"}` unless the messages
    contain the literal word "json". JSON mode is set on the model's `parameters`,
    so *every* task-building path must satisfy that — otherwise the request 400s
    against the live API while demo mode passes happily. This regression covers
    the native `LinearSyncPipeline` route, which built tasks from the agent's raw
    instructions and did exactly that.
    """
    from app.agents.contract_agents import AGENT_CLASSES

    for cls in AGENT_CLASSES:
        agent = cls()
        if not agent.schema_hint:
            continue  # prose agents do not run in JSON mode

        task = agent.build_task(default_input="{}")
        assert "json" in task.instructions.lower(), (
            f"{cls.__name__} builds a JSON-mode task whose instructions never say "
            f"'json'; the live OpenAI call would fail with a 400."
        )
        assert "json" in agent._prompt("{}").lower(), (
            f"{cls.__name__}'s direct prompt path omits the JSON contract."
        )


def test_json_contract_is_not_duplicated_when_already_present() -> None:
    """Passing instructions that already mention JSON must not append a second copy."""
    from app.agents.contract_agents import ClauseClassificationAgent

    agent = ClauseClassificationAgent()
    custom = "Return the category as JSON."
    assert agent._instructions_for(custom) == custom
