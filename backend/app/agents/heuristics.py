"""
Deterministic clause analysis: classification, risk scoring, playbook evaluation.

This module is pure and has no LLM or network dependency, which makes it three
useful things at once:

  1. **A fallback.** When an LLM call fails or returns unparseable output, the
     agents degrade to these functions instead of the pipeline collapsing.
  2. **Demo mode.** Powers believable, deterministic output with no API key —
     so the demo and the Playwright e2e test never depend on the network.
  3. **The unit-test surface.** `tests/test_classification.py` and
     `tests/test_risk_scoring.py` test this logic directly, because assertions
     about deterministic functions are worth something, while assertions about
     a live model's prose are not.

Scores are 0–100, where higher means more risk to *our* side of the deal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.domain import (
    CATEGORY_KEYWORDS,
    ClauseCategory,
    RiskLevel,
    category_weight,
    risk_level_for_score,
)

# ─────────────────────────────────────────────────────────────────────────────
# Value extraction
# ─────────────────────────────────────────────────────────────────────────────

_MULTIPLIERS = {
    "k": 1_000, "thousand": 1_000,
    "m": 1_000_000, "mm": 1_000_000, "million": 1_000_000,
    "b": 1_000_000_000, "bn": 1_000_000_000, "billion": 1_000_000_000,
}

# $100,000 / $1.5 million / USD 250,000 / 50,000 USD / $2M
_MONEY_RE = re.compile(
    r"""
    (?:
        (?:US\$|USD|\$|EUR|GBP|£|€)\s*
        (?P<amt1>\d[\d,]*(?:\.\d+)?)
        \s*(?P<mult1>k|m|mm|bn|b|thousand|million|billion)?
      |
        (?P<amt2>\d[\d,]*(?:\.\d+)?)
        \s*(?P<mult2>k|m|mm|bn|b|thousand|million|billion)?
        \s*(?:US\$|USD|dollars|EUR|euros|GBP|pounds)
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

_WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "fifteen": 15, "eighteen": 18, "twenty": 20, "thirty": 30, "forty": 40,
    "forty-five": 45, "sixty": 60, "ninety": 90, "one hundred twenty": 120,
}

_DURATION_RE = re.compile(
    r"(?P<num>\d+|[a-z\-]+)\s*(?:\(\s*(?P<paren>\d+)\s*\)\s*)?"
    r"(?P<unit>day|days|week|weeks|month|months|year|years)",
    re.IGNORECASE,
)


def extract_money(text: str) -> List[float]:
    """Return every monetary amount in `text`, normalised to units.

    Handles `$100,000`, `$1.5 million`, `$2M`, `USD 250,000`, `50,000 dollars`.
    """
    found: List[float] = []
    for m in _MONEY_RE.finditer(text or ""):
        raw = m.group("amt1") or m.group("amt2")
        mult = (m.group("mult1") or m.group("mult2") or "").lower()
        if not raw:
            continue
        try:
            value = float(raw.replace(",", ""))
        except ValueError:
            continue
        if mult:
            value *= _MULTIPLIERS.get(mult, 1)
        found.append(value)
    return found


def max_money(text: str) -> Optional[float]:
    amounts = extract_money(text)
    return max(amounts) if amounts else None


def extract_durations_days(text: str) -> List[int]:
    """Return durations found in `text`, normalised to days."""
    out: List[int] = []
    unit_days = {"day": 1, "week": 7, "month": 30, "year": 365}
    for m in _DURATION_RE.finditer(text or ""):
        # "thirty (30) days" — prefer the digits in parentheses.
        num_raw = m.group("paren") or m.group("num")
        if num_raw is None:
            continue
        num_raw = num_raw.lower().strip()
        if num_raw.isdigit():
            n = int(num_raw)
        elif num_raw in _WORD_NUMBERS:
            n = _WORD_NUMBERS[num_raw]
        else:
            continue
        unit = m.group("unit").lower().rstrip("s")
        out.append(n * unit_days.get(unit, 1))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Classification
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ClassificationResult:
    category: str
    confidence: float
    signals: List[str] = field(default_factory=list)
    alternatives: List[Dict[str, Any]] = field(default_factory=list)
    method: str = "heuristic"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "confidence": round(self.confidence, 3),
            "signals": self.signals,
            "alternatives": self.alternatives,
            "method": self.method,
        }


# Headings are strong evidence; a clause titled "Limitation of Liability" is one.
_HEADING_RE = re.compile(
    r"^\s*(?:(?:section\s+)?\d+(?:\.\d+)*\.?\s*|article\s+[ivxlc\d]+\.?\s*)?"
    r"(?P<title>[A-Z][A-Za-z /&'\-]{2,60}?)\s*(?:[:.—-]|\n)",
)


def _heading_of(text: str) -> str:
    m = _HEADING_RE.match(text or "")
    return (m.group("title").strip().lower() if m else "")


def classify_clause_heuristic(text: str) -> ClassificationResult:
    """Score a clause against per-category keyword signals.

    Confidence reflects both absolute evidence and how far the winner leads the
    runner-up, so a clause matching two categories equally reports low
    confidence — which the hallucination guardrail then surfaces for review.
    """
    body = (text or "").lower()
    if not body.strip():
        return ClassificationResult(ClauseCategory.OTHER.value, 0.0, ["empty clause"])

    heading = _heading_of(text)
    scores: Dict[str, float] = {}
    hits: Dict[str, List[str]] = {}

    for category, keywords in CATEGORY_KEYWORDS.items():
        score = 0.0
        matched: List[str] = []
        for kw in keywords:
            if kw in body:
                # Longer phrases are more discriminating than single words.
                weight = 2.5 if " " in kw else 1.0
                score += weight
                matched.append(kw)
                # A keyword in the heading is much stronger evidence.
                if heading and kw in heading:
                    score += 3.0
        if score > 0:
            scores[category] = score
            hits[category] = matched

    if not scores:
        return ClassificationResult(
            ClauseCategory.OTHER.value, 0.25, ["no category keywords matched"]
        )

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top_cat, top_score = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0.0

    # Absolute evidence saturating around 8 points.
    evidence = min(top_score / 8.0, 1.0)
    # Separation from the runner-up.
    margin = (top_score - runner_up) / top_score if top_score else 0.0
    confidence = 0.35 + (0.40 * evidence) + (0.25 * margin)
    confidence = max(0.0, min(0.99, confidence))

    alternatives = [
        {"category": c, "score": round(s, 2)} for c, s in ranked[1:4]
    ]
    return ClassificationResult(
        category=top_cat,
        confidence=confidence,
        signals=hits.get(top_cat, [])[:6],
        alternatives=alternatives,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Risk signals
# ─────────────────────────────────────────────────────────────────────────────

# (pattern, risk points, human-readable finding)
_RED_FLAGS: List[Tuple[str, int, str]] = [
    (r"unlimited liability", 40, "Unlimited liability exposure"),
    (r"shall not be (?:subject to any|limited by any) (?:cap|limit)", 35,
     "Liability expressly uncapped"),
    (r"no (?:limitation|cap) on (?:liability|damages)", 35, "No cap on damages"),
    (r"sole discretion", 18, "Counterparty acts at its sole discretion"),
    (r"perpetual(?:,| and)? irrevocable", 25, "Perpetual irrevocable grant"),
    (r"assigns? all right,? title,? and interest", 28,
     "Full assignment of IP ownership"),
    (r"exclusive license", 18, "Exclusivity granted"),
    (r"automatically renew", 20, "Automatic renewal"),
    (r"without (?:prior )?(?:written )?notice", 22, "Action permitted without notice"),
    (r"immediately (?:terminate|upon notice)", 18, "Immediate termination right"),
    (r"terminate .{0,40}for convenience", 15, "Termination for convenience"),
    (r"indemnif\w+ .{0,60}(?:any and all|all) claims", 30, "Broad indemnity scope"),
    (r"defend,? indemnify,? and hold harmless", 22, "Full defend-and-indemnify duty"),
    (r"as is,? without (?:any )?warrant", 25, "Goods/services provided as-is"),
    (r"disclaims? all warrant", 22, "All warranties disclaimed"),
    (r"waive[sd]? .{0,30}(?:jury trial|right to a jury)", 20, "Jury trial waived"),
    (r"class action waiver", 18, "Class action waiver"),
    (r"liquidated damages", 20, "Liquidated damages imposed"),
    (r"joint and several", 18, "Joint and several liability"),
    (r"net (?:60|90|120)", 18, "Extended payment terms"),
    (r"non-?refundable", 15, "Non-refundable amounts"),
    (r"unilaterally (?:amend|modify|change)", 28, "Unilateral amendment right"),
    (r"no right to (?:audit|inspect)", 15, "Audit rights denied"),
    (r"shall not compete", 20, "Non-compete restriction"),
    (r"irrevocabl\w+ waive", 20, "Irrevocable waiver"),
    (r"consequential,? (?:incidental,? )?(?:or )?punitive damages", 12,
     "Consequential damages addressed"),
]

# (pattern, points removed, human-readable finding)
_MITIGATORS: List[Tuple[str, int, str]] = [
    (r"(?:liability|damages) .{0,40}(?:capped|limited) (?:at|to)", 22,
     "Liability is capped"),
    (r"mutual(?:ly)? (?:indemnif|agree|confidential)", 15, "Mutual obligation"),
    (r"each party", 10, "Symmetric obligation"),
    (r"upon (?:thirty|sixty|ninety|\d+)\s*(?:\(\d+\))?\s*days'? (?:prior )?written notice",
     14, "Advance written notice required"),
    (r"prior written consent", 12, "Requires prior written consent"),
    (r"cure period", 12, "Cure period available"),
    (r"reasonable (?:efforts|care|notice)", 8, "Reasonableness standard applies"),
    (r"net (?:15|30)\b", 10, "Standard payment terms"),
    (r"pro-?rata refund", 10, "Pro-rata refund available"),
    (r"may terminate .{0,40}for cause", 8, "Termination limited to cause"),
]

# Where each category starts before signals are applied.
_CATEGORY_BASELINE: Dict[str, int] = {
    ClauseCategory.LIABILITY.value: 42,
    ClauseCategory.INDEMNIFICATION.value: 40,
    ClauseCategory.IP.value: 36,
    ClauseCategory.DATA_PRIVACY.value: 35,
    ClauseCategory.PAYMENT.value: 28,
    ClauseCategory.TERMINATION.value: 30,
    ClauseCategory.NON_COMPETE.value: 34,
    ClauseCategory.WARRANTY.value: 30,
    ClauseCategory.CONFIDENTIALITY.value: 24,
    ClauseCategory.SLA.value: 26,
    ClauseCategory.RENEWAL.value: 26,
    ClauseCategory.INSURANCE.value: 22,
    ClauseCategory.COMPLIANCE.value: 22,
    ClauseCategory.DISPUTE_RESOLUTION.value: 24,
    ClauseCategory.ASSIGNMENT.value: 22,
    ClauseCategory.AUDIT_RIGHTS.value: 20,
    ClauseCategory.GOVERNING_LAW.value: 16,
    ClauseCategory.FORCE_MAJEURE.value: 14,
    ClauseCategory.DEFINITIONS.value: 8,
    ClauseCategory.OTHER.value: 18,
}

DEFAULT_BASELINE = 20


@dataclass
class RiskFinding:
    code: str
    detail: str
    points: int
    source: str  # "signal" | "mitigator" | "playbook"
    rule_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "detail": self.detail,
            "points": self.points,
            "source": self.source,
            "rule_id": self.rule_id,
        }


@dataclass
class RiskResult:
    score: float
    level: str
    findings: List[RiskFinding] = field(default_factory=list)
    rationale: str = ""
    triggered_rule_ids: List[str] = field(default_factory=list)
    method: str = "heuristic"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": round(self.score, 1),
            "level": self.level,
            "findings": [f.to_dict() for f in self.findings],
            "rationale": self.rationale,
            "triggered_rule_ids": self.triggered_rule_ids,
            "method": self.method,
        }


def evaluate_playbook_rules(
    text: str, category: str, rules: Iterable[Dict[str, Any]]
) -> List[RiskFinding]:
    """Apply admin-authored playbook rules to one clause.

    Supported `rule_type`s:
      * `monetary_threshold`  — compare the largest amount in the clause
      * `duration_threshold`  — compare the longest duration (in days)
      * `forbidden_language`  — any listed keyword present  → fires
      * `required_language`   — no listed keyword present   → fires
    """
    findings: List[RiskFinding] = []
    body = (text or "").lower()

    for rule in rules or []:
        rule_category = rule.get("category")
        # A rule scoped to a category only applies to that category.
        if rule_category and rule_category not in ("*", "Any", category):
            continue

        rule_type = (rule.get("rule_type") or "").strip()

        # A `required_language` rule fires on the ABSENCE of wording, so a
        # wildcard-scoped one would fire on every clause that isn't about its
        # subject — e.g. "governing law must name a recognised jurisdiction"
        # would flag the payment clause, the IP clause and the preamble alike.
        # Requiring language only makes sense within a specific clause type, so
        # wildcard required-language rules are skipped rather than allowed to
        # inflate every score in the contract.
        if rule_type == "required_language" and rule_category in ("*", "Any", None, ""):
            continue
        points = int(rule.get("risk_points") or 20)
        title = rule.get("title") or rule.get("id") or "playbook rule"
        rule_id = str(rule.get("id") or title)
        fired = False
        detail = ""

        if rule_type == "monetary_threshold":
            threshold = rule.get("threshold")
            observed = max_money(text)
            if threshold is not None and observed is not None:
                if _compare(observed, rule.get("operator", "gt"), float(threshold)):
                    fired = True
                    detail = (
                        f"{title}: clause value ${observed:,.0f} "
                        f"{_op_words(rule.get('operator', 'gt'))} "
                        f"threshold ${float(threshold):,.0f}"
                    )

        elif rule_type == "duration_threshold":
            threshold = rule.get("threshold")
            durations = extract_durations_days(text)
            if threshold is not None and durations:
                observed = max(durations)
                if _compare(observed, rule.get("operator", "gt"), float(threshold)):
                    fired = True
                    detail = (
                        f"{title}: duration {observed} days "
                        f"{_op_words(rule.get('operator', 'gt'))} "
                        f"threshold {int(float(threshold))} days"
                    )

        elif rule_type == "forbidden_language":
            matched = [k for k in (rule.get("keywords") or []) if k.lower() in body]
            if matched:
                fired = True
                detail = f"{title}: contains prohibited language ({', '.join(matched[:3])})"

        elif rule_type == "required_language":
            keywords = [k.lower() for k in (rule.get("keywords") or [])]
            if keywords and not any(k in body for k in keywords):
                fired = True
                detail = (
                    f"{title}: missing required language "
                    f"({', '.join(keywords[:3])})"
                )

        if fired:
            findings.append(
                RiskFinding(
                    code=rule_type or "playbook",
                    detail=detail,
                    points=points,
                    source="playbook",
                    rule_id=rule_id,
                )
            )

    return findings


def _compare(observed: float, operator: str, threshold: float) -> bool:
    op = (operator or "gt").lower()
    if op in ("gt", ">"):
        return observed > threshold
    if op in ("gte", ">="):
        return observed >= threshold
    if op in ("lt", "<"):
        return observed < threshold
    if op in ("lte", "<="):
        return observed <= threshold
    if op in ("eq", "=="):
        return observed == threshold
    return False


def _op_words(operator: str) -> str:
    return {
        "gt": "exceeds", ">": "exceeds",
        "gte": "meets or exceeds", ">=": "meets or exceeds",
        "lt": "is below", "<": "is below",
        "lte": "is at or below", "<=": "is at or below",
        "eq": "equals", "==": "equals",
    }.get((operator or "gt").lower(), "compares against")


def score_clause_heuristic(
    text: str,
    category: str,
    playbook_rules: Optional[Iterable[Dict[str, Any]]] = None,
    *,
    high_threshold: int = 70,
    medium_threshold: int = 40,
) -> RiskResult:
    """Score one clause 0–100 from its baseline, signals, and playbook rules."""
    body = (text or "")
    if not body.strip():
        return RiskResult(0.0, RiskLevel.LOW.value, [], "Empty clause; nothing to score.")

    lowered = body.lower()
    score = float(_CATEGORY_BASELINE.get(category, DEFAULT_BASELINE))
    findings: List[RiskFinding] = []

    for pattern, points, label in _RED_FLAGS:
        if re.search(pattern, lowered):
            score += points
            findings.append(RiskFinding("red_flag", label, points, "signal"))

    for pattern, points, label in _MITIGATORS:
        if re.search(pattern, lowered):
            score -= points
            findings.append(RiskFinding("mitigator", label, -points, "mitigator"))

    playbook_findings = evaluate_playbook_rules(body, category, playbook_rules or [])
    for f in playbook_findings:
        score += f.points
    findings.extend(playbook_findings)

    score = max(0.0, min(100.0, score))
    level = risk_level_for_score(score, high_threshold, medium_threshold)

    drivers = [f.detail for f in findings if f.points > 0][:3]
    protections = [f.detail for f in findings if f.points < 0][:2]
    parts = [f"{category} clause scored {score:.0f}/100 ({level.value} risk)"]
    if drivers:
        parts.append("driven by " + "; ".join(drivers))
    if protections:
        parts.append("partially mitigated by " + "; ".join(protections))
    if not drivers and not protections:
        parts.append("no material risk signals detected; scored at category baseline")

    return RiskResult(
        score=score,
        level=level.value,
        findings=findings,
        rationale=". ".join(parts) + ".",
        triggered_rule_ids=[f.rule_id for f in playbook_findings if f.rule_id],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Contract-level rollup
# ─────────────────────────────────────────────────────────────────────────────


def aggregate_contract_risk(
    clause_scores: Iterable[Dict[str, Any]],
    *,
    high_threshold: int = 70,
    medium_threshold: int = 40,
) -> Dict[str, Any]:
    """Roll clause scores into one contract score.

    A category-weighted mean, then a penalty for concentration of severe
    clauses — because ten benign clauses should not average away one
    deal-breaking indemnity. The penalty is capped so it cannot alone
    manufacture a Critical rating.
    """
    items = [c for c in clause_scores if c is not None]
    if not items:
        return {
            "score": 0.0,
            "level": RiskLevel.LOW.value,
            "clause_count": 0,
            "weighted_mean": 0.0,
            "severity_penalty": 0.0,
            "distribution": {lvl.value: 0 for lvl in RiskLevel},
        }

    total_weight = 0.0
    weighted_sum = 0.0
    distribution: Dict[str, int] = {lvl.value: 0 for lvl in RiskLevel}

    for c in items:
        score = float(c.get("score") or 0.0)
        weight = category_weight(str(c.get("category") or ""))
        weighted_sum += score * weight
        total_weight += weight
        lvl = str(c.get("level") or risk_level_for_score(score).value)
        if lvl in distribution:
            distribution[lvl] += 1

    weighted_mean = weighted_sum / total_weight if total_weight else 0.0

    severe = distribution[RiskLevel.HIGH.value] + distribution[RiskLevel.CRITICAL.value]
    ratio = severe / len(items)
    severity_penalty = min(18.0, ratio * 30.0)

    score = max(0.0, min(100.0, weighted_mean + severity_penalty))
    return {
        "score": round(score, 1),
        "level": risk_level_for_score(score, high_threshold, medium_threshold).value,
        "clause_count": len(items),
        "weighted_mean": round(weighted_mean, 1),
        "severity_penalty": round(severity_penalty, 1),
        "distribution": distribution,
    }
