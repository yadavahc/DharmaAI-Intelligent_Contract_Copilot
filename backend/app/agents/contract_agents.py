"""
The Dharma AI agent roster — every agent, in one file, for easy inspection.

Each class is a real Lyzr agent: it owns a `lyzr_automata.Agent` (role +
prompt_persona) and emits `lyzr_automata.Task` objects that run inside a
`LinearSyncPipeline` (see `pipeline.py`).

    ┌───────────────────────── ingest ─────────────────────────┐
    ContractParsingAgent → ClauseClassificationAgent → PlaybookValidationAgent
                                                              → RiskAssessmentAgent
                                                              → RedlineAgent
    ┌────────────────────── negotiate ─────────────────────────┐
    OrganizationNegotiatorAgent ⇄ CounterpartyNegotiatorAgent
                    (N rounds, refereed by NegotiationStrategyCoachAgent)
                                  ↓
    EscalationAgent → human reviewer queue → AuditAgent (records everything)

Every agent degrades to `heuristics.py` rather than raising, so one bad LLM
response cannot take down a pipeline mid-demo. Each returns a `confidence`
value, which the hallucination guardrail thresholds.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional

from app.agents import roles
from app.agents.base import DharmaAgent, clamp
from app.agents.heuristics import (
    ClassificationResult,
    aggregate_contract_risk,
    classify_clause_heuristic,
    score_clause_heuristic,
)
from app.config import settings
from app.domain import ClauseCategory, RiskLevel, risk_level_for_score

LOW_CONFIDENCE_THRESHOLD = 0.55


# ─────────────────────────────────────────────────────────────────────────────
# 1. Contract Parsing
# ─────────────────────────────────────────────────────────────────────────────


class ContractParsingAgent(DharmaAgent):
    """Reads the raw document and pulls out contract-level metadata."""

    key = "contract_parsing"
    name = "Contract Parsing Agent"
    role = roles.CONTRACT_PARSER
    persona = (
        "a meticulous contracts paralegal who reads documents structurally. You "
        "identify parties, dates, governing law and document type from the four "
        "corners of the text. You never invent a fact that is not present; if a "
        "detail is absent you say so explicitly."
    )
    instructions = (
        "Extract contract-level metadata from the supplied document text. Identify "
        "the document title, the contracting parties with their roles, the effective "
        "date, the governing law, the term, and the document type. Where a field is "
        "not stated in the text, return the string 'not stated' rather than guessing"
    )
    schema_hint = (
        '{"title": str, "parties": [str], "effective_date": str, '
        '"governing_law": str, "term": str, "document_type": str, '
        '"confidence": float 0-1}'
    )
    outputs = "Contract metadata: title, parties, dates, governing law, document type"
    hands_off_to = ["clause_classification"]
    temperature = 0.1

    def parse(self, document_text: str, filename: str = "") -> Dict[str, Any]:
        payload = json.dumps(
            {"filename": filename, "text": document_text[:6000]}, ensure_ascii=False
        )
        fallback = {
            "title": filename or "Untitled Agreement",
            "parties": [],
            "effective_date": "not stated",
            "governing_law": "not stated",
            "term": "not stated",
            "document_type": "Agreement",
            "confidence": 0.3,
        }
        result = self.run_json(payload, fallback=fallback)
        if not isinstance(result, dict):
            return fallback
        result.setdefault("title", filename or "Untitled Agreement")
        parties = result.get("parties")
        if isinstance(parties, str):
            result["parties"] = [parties]
        elif not isinstance(parties, list):
            result["parties"] = []
        result["confidence"] = clamp(result.get("confidence"), 0.0, 1.0, 0.6)
        return result


# ─────────────────────────────────────────────────────────────────────────────
# 2. Clause Classification
# ─────────────────────────────────────────────────────────────────────────────


class ClauseClassificationAgent(DharmaAgent):
    """Tags each clause with a category and a calibrated confidence score."""

    key = "clause_classification"
    name = "Clause Classification Agent"
    role = roles.CLAUSE_CLASSIFIER
    persona = (
        "a commercial contracts attorney who has classified tens of thousands of "
        "clauses. You judge a clause by its operative effect, not its heading — a "
        "clause titled 'Miscellaneous' that caps damages is a Liability clause. You "
        "report honest confidence: when a clause genuinely spans two categories you "
        "say so rather than forcing false precision."
    )
    instructions = (
        "Classify the supplied contract clause into exactly one category from the "
        "allowed list. Return the category, a calibrated confidence between 0 and 1, "
        "a one-sentence rationale citing the specific language that drove the "
        "decision, up to two plausible alternative categories, and the key operative "
        "terms you relied on"
    )
    schema_hint = (
        '{"category": one of ' + json.dumps(ClauseCategory.values()) + ", "
        '"confidence": float 0-1, "rationale": str, '
        '"alternatives": [{"category": str, "score": float}], "key_terms": [str]}'
    )
    outputs = "Clause category + confidence + rationale + alternatives"
    hands_off_to = ["playbook_validation", "risk_assessment"]
    temperature = 0.1

    def classify(self, clause_text: str, heading: str = "") -> Dict[str, Any]:
        heuristic: ClassificationResult = classify_clause_heuristic(clause_text)
        payload = json.dumps(
            {
                "heading": heading,
                "clause_text": clause_text[:4000],
                "allowed_categories": ClauseCategory.values(),
            },
            ensure_ascii=False,
        )
        result = self.run_json(payload, fallback=None)

        if not isinstance(result, dict) or not result.get("category"):
            out = heuristic.to_dict()
            out["rationale"] = (
                "Classified by deterministic keyword analysis "
                f"({', '.join(heuristic.signals[:3]) or 'no strong signals'}); "
                "the language model did not return a usable classification."
            )
            out["method"] = "heuristic-fallback"
            out["key_terms"] = heuristic.signals[:5]
            return out

        category = str(result.get("category", "")).strip()
        # Reject an out-of-taxonomy label rather than storing an unknown string.
        if category not in ClauseCategory.values():
            category = heuristic.category

        confidence = clamp(result.get("confidence"), 0.0, 1.0, heuristic.confidence)

        # Model and heuristic disagreeing is real evidence of ambiguity; damp the
        # confidence so the hallucination guardrail can catch it.
        if category != heuristic.category and heuristic.confidence > 0.6:
            confidence = min(confidence, 0.62)

        alternatives = result.get("alternatives")
        if not isinstance(alternatives, list):
            alternatives = heuristic.alternatives[:2]

        return {
            "category": category,
            "confidence": round(confidence, 3),
            "rationale": str(result.get("rationale") or "")[:600],
            "alternatives": alternatives[:3],
            "key_terms": (result.get("key_terms") if isinstance(result.get("key_terms"), list) else [])[:6],
            "signals": heuristic.signals[:6],
            "heuristic_category": heuristic.category,
            "heuristic_confidence": round(heuristic.confidence, 3),
            "method": "llm+heuristic",
        }


# ─────────────────────────────────────────────────────────────────────────────
# 3. Playbook Validation
# ─────────────────────────────────────────────────────────────────────────────


class PlaybookValidationAgent(DharmaAgent):
    """Checks a clause against the admin playbook rules retrieved from Qdrant."""

    key = "playbook_validation"
    name = "Playbook Validation Agent"
    role = roles.PLAYBOOK_VALIDATOR
    persona = (
        "a compliance officer who owns the company's contract playbook. You apply "
        "the written rules literally and refuse to improvise: a rule either fires on "
        "this clause or it does not. You always cite the rule id you relied on."
    )
    instructions = (
        "Validate the supplied clause against the retrieved playbook rules. For each "
        "rule that the clause breaches, report the rule id, what specifically "
        "breaches it, and the severity. Judge only against the rules provided — do "
        "not invent policy. Cite rule ids exactly as given"
    )
    schema_hint = (
        '{"compliant": bool, "violations": [{"rule_id": str, "detail": str, '
        '"severity": "Low"|"Medium"|"High"}], "matched_rule_ids": [str], '
        '"assessment": str, "confidence": float 0-1}'
    )
    outputs = "Compliance verdict + violated rule ids + severity"
    hands_off_to = ["risk_assessment"]
    uses_qdrant = True
    qdrant_purpose = (
        "Semantic retrieval of the playbook rules most relevant to this clause, so "
        "the agent sees the handful of rules that matter instead of the whole book."
    )
    temperature = 0.1

    def validate(
        self,
        clause_text: str,
        category: str,
        playbook_rules: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        # Deterministic evaluation always runs: monetary and duration thresholds
        # are arithmetic, and arithmetic should not be delegated to a language model.
        deterministic = score_clause_heuristic(clause_text, category, playbook_rules)
        deterministic_violations = [
            {
                "rule_id": f.rule_id,
                "detail": f.detail,
                "severity": "High" if f.points >= 25 else "Medium",
                "source": "deterministic",
            }
            for f in deterministic.findings
            if f.source == "playbook"
        ]

        payload = json.dumps(
            {
                "category": category,
                "clause_text": clause_text[:3000],
                "playbook_rules": playbook_rules[:8],
            },
            ensure_ascii=False,
        )
        result = self.run_json(payload, fallback=None)

        llm_violations: List[Dict[str, Any]] = []
        assessment = ""
        confidence = 0.6
        if isinstance(result, dict):
            raw = result.get("violations")
            if isinstance(raw, list):
                valid_ids = {str(r.get("id")) for r in playbook_rules}
                for v in raw:
                    if not isinstance(v, dict):
                        continue
                    # Drop hallucinated rule ids — a cited rule must exist.
                    if str(v.get("rule_id")) not in valid_ids:
                        continue
                    llm_violations.append(
                        {
                            "rule_id": str(v.get("rule_id")),
                            "detail": str(v.get("detail") or "")[:400],
                            "severity": str(v.get("severity") or "Medium"),
                            "source": "llm",
                        }
                    )
            assessment = str(result.get("assessment") or "")[:600]
            confidence = clamp(result.get("confidence"), 0.0, 1.0, 0.7)

        # Union, deterministic winning on conflict.
        merged: Dict[str, Dict[str, Any]] = {v["rule_id"]: v for v in llm_violations}
        for v in deterministic_violations:
            merged[str(v["rule_id"])] = v
        violations = list(merged.values())

        return {
            "compliant": not violations,
            "violations": violations,
            "matched_rule_ids": [str(r.get("id")) for r in playbook_rules][:10],
            "assessment": assessment
            or (
                f"Clause satisfies all {len(playbook_rules)} retrieved rules."
                if not violations
                else f"Clause breaches {len(violations)} of {len(playbook_rules)} retrieved rules."
            ),
            "confidence": round(confidence, 3),
            "deterministic_score": round(deterministic.score, 1),
        }


# ─────────────────────────────────────────────────────────────────────────────
# 4. Risk Assessment
# ─────────────────────────────────────────────────────────────────────────────


class RiskAssessmentAgent(DharmaAgent):
    """Scores a clause against the playbook and explains the score."""

    key = "risk_assessment"
    name = "Risk Assessment Agent"
    role = roles.RISK_ASSESSOR
    persona = (
        "a risk analyst advising in-house counsel. You quantify exposure from our "
        "side of the deal on a 0-100 scale where 100 is existential. You are "
        "specific about the mechanism of harm — not 'this is risky' but 'this "
        "permits termination on 5 days notice with no cure period, stranding "
        "in-flight work'. Every score comes with a concrete suggested fix."
    )
    instructions = (
        "Assess the risk this clause poses to our organisation. Return a risk score "
        "from 0 to 100, a risk level, a specific explanation naming the mechanism of "
        "harm, a concrete suggested fix in contract language, and the financial "
        "exposure if quantifiable. Weigh the retrieved playbook rules heavily — a "
        "clause that breaches an explicit rule is high risk by definition"
    )
    schema_hint = (
        '{"risk_score": int 0-100, "risk_level": "Low"|"Medium"|"High"|"Critical", '
        '"explanation": str, "suggested_fix": str, "financial_exposure": str, '
        '"triggered_rule_ids": [str], "confidence": float 0-1}'
    )
    outputs = "Risk score 0-100 + level + explanation + suggested fix"
    hands_off_to = ["redline", "escalation"]
    uses_qdrant = True
    qdrant_purpose = (
        "Retrieves the applicable playbook rules and similar historical clauses so "
        "scoring is grounded in company policy and precedent, not model intuition."
    )
    temperature = 0.2

    def assess(
        self,
        clause_text: str,
        category: str,
        playbook_rules: Optional[List[Dict[str, Any]]] = None,
        similar_clauses: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        rules = playbook_rules or []
        baseline = score_clause_heuristic(
            clause_text,
            category,
            rules,
            high_threshold=settings.risk_high_threshold,
            medium_threshold=settings.risk_medium_threshold,
        )

        payload = json.dumps(
            {
                "category": category,
                "clause_text": clause_text[:3000],
                "playbook_rules": rules[:8],
                "similar_historical_clauses": [
                    {
                        "text": str(s.get("text") or "")[:400],
                        "risk_level": s.get("risk_level"),
                        "similarity": s.get("score"),
                    }
                    for s in (similar_clauses or [])[:3]
                ],
                "deterministic_baseline": {
                    "score": baseline.score,
                    "level": baseline.level,
                    "findings": [f.detail for f in baseline.findings][:6],
                },
            },
            ensure_ascii=False,
        )
        result = self.run_json(payload, fallback=None)

        if not isinstance(result, dict) or result.get("risk_score") is None:
            out = baseline.to_dict()
            return {
                "risk_score": round(baseline.score, 1),
                "risk_level": baseline.level,
                "explanation": baseline.rationale,
                "suggested_fix": _fallback_fix(category),
                "financial_exposure": "not quantified",
                "triggered_rule_ids": baseline.triggered_rule_ids,
                "findings": [f.to_dict() for f in baseline.findings],
                "confidence": 0.5,
                "method": "heuristic-fallback",
                "deterministic_score": round(baseline.score, 1),
            }

        llm_score = clamp(result.get("risk_score"), 0, 100, baseline.score)

        # Blend model judgement with the deterministic baseline (60/40). The
        # baseline anchors the score to policy arithmetic; the model contributes
        # reading comprehension. Pure-LLM scores drift badly between runs.
        blended = (0.6 * llm_score) + (0.4 * baseline.score)

        # A fired playbook rule sets a floor — policy is not negotiable by vibes.
        if baseline.triggered_rule_ids:
            blended = max(blended, float(settings.risk_high_threshold))

        level = risk_level_for_score(
            blended, settings.risk_high_threshold, settings.risk_medium_threshold
        ).value

        return {
            "risk_score": round(blended, 1),
            "risk_level": level,
            "explanation": str(result.get("explanation") or baseline.rationale)[:1200],
            "suggested_fix": str(result.get("suggested_fix") or _fallback_fix(category))[:800],
            "financial_exposure": str(result.get("financial_exposure") or "not quantified")[:200],
            "triggered_rule_ids": (
                result.get("triggered_rule_ids")
                if isinstance(result.get("triggered_rule_ids"), list)
                else baseline.triggered_rule_ids
            ),
            "findings": [f.to_dict() for f in baseline.findings],
            "confidence": round(clamp(result.get("confidence"), 0.0, 1.0, 0.75), 3),
            "llm_score": round(llm_score, 1),
            "deterministic_score": round(baseline.score, 1),
            "method": "llm+heuristic-blend",
        }

    @staticmethod
    def rollup(clause_scores: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        return aggregate_contract_risk(
            clause_scores,
            high_threshold=settings.risk_high_threshold,
            medium_threshold=settings.risk_medium_threshold,
        )


def _fallback_fix(category: str) -> str:
    return (
        f"Rebalance this {category} provision: introduce reciprocal obligations, a "
        "defined notice period, and an express cap on exposure."
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5. Redline
# ─────────────────────────────────────────────────────────────────────────────


class RedlineAgent(DharmaAgent):
    """Produces original → suggested → reason for the diff view."""

    key = "redline"
    name = "Redline Agent"
    role = roles.REDLINE_DRAFTER
    persona = (
        "a senior drafting attorney. You rewrite clauses in the register and defined "
        "terms of the original document, changing only what must change. You never "
        "rewrite a clause wholesale when a targeted amendment achieves the same "
        "protection, because every extra edit is another thing the counterparty "
        "argues about."
    )
    instructions = (
        "Redraft the supplied clause to remove the identified risk. Return the "
        "original text verbatim, your suggested replacement text, and a plain-English "
        "reason a business stakeholder would understand. Preserve the document's "
        "defined terms, numbering and drafting style. Make the minimum change that "
        "achieves the protection"
    )
    schema_hint = (
        '{"original": str, "suggested": str, "reason": str, "change_summary": str, '
        '"materiality": "low"|"medium"|"high", "confidence": float 0-1}'
    )
    outputs = "original → suggested → reason (rendered as a diff)"
    hands_off_to = ["organization_negotiator", "escalation"]
    uses_qdrant = True
    qdrant_purpose = (
        "Precedent Recall: retrieves previously *approved* clause wording for this "
        "category so suggestions reuse language the company has already accepted."
    )
    temperature = 0.3

    def draft(
        self,
        clause_text: str,
        category: str,
        risk_explanation: str = "",
        suggested_fix: str = "",
        precedents: Optional[List[Dict[str, Any]]] = None,
        risk_level: str = RiskLevel.MEDIUM.value,
    ) -> Dict[str, Any]:
        payload = json.dumps(
            {
                "category": category,
                "risk_level": risk_level,
                "original": clause_text[:3000],
                "risk_explanation": risk_explanation[:800],
                "target_fix": suggested_fix[:600],
                "approved_precedent_language": [
                    {"text": str(p.get("text") or "")[:500], "similarity": p.get("score")}
                    for p in (precedents or [])[:3]
                ],
            },
            ensure_ascii=False,
        )
        result = self.run_json(payload, fallback=None)

        if not isinstance(result, dict) or not result.get("suggested"):
            return {
                "original": clause_text,
                "suggested": clause_text,
                "reason": (
                    "The redline agent could not produce a confident revision for "
                    "this clause. Flagged for human drafting."
                ),
                "change_summary": "No automated change proposed.",
                "materiality": "low",
                "confidence": 0.3,
                "method": "no-change-fallback",
                "used_precedent": False,
            }

        suggested = str(result.get("suggested") or "").strip()
        return {
            # Always echo the true original; never trust the model's copy of it.
            "original": clause_text,
            "suggested": suggested[:6000],
            "reason": str(result.get("reason") or "")[:1000],
            "change_summary": str(result.get("change_summary") or "")[:400],
            "materiality": str(result.get("materiality") or "medium"),
            "confidence": round(clamp(result.get("confidence"), 0.0, 1.0, 0.7), 3),
            "unchanged": suggested.strip() == clause_text.strip(),
            "used_precedent": bool(precedents),
            "precedent_count": len(precedents or []),
            "method": "llm",
        }


# ─────────────────────────────────────────────────────────────────────────────
# 6 & 7. The two negotiators
# ─────────────────────────────────────────────────────────────────────────────


class _NegotiatorAgent(DharmaAgent):
    """Shared behaviour for the two opposing negotiators."""

    schema_hint = (
        '{"message": str, "stance": "counter"|"accept"|"reject"|"escalate", '
        '"proposed_language": str, "concession": str, "rationale": str, '
        '"projected_risk_score": int 0-100, "confidence": float 0-1}'
    )
    outputs = "Negotiation message + stance + proposed language + projected risk"
    temperature = 0.6

    def negotiate(
        self,
        clause_text: str,
        category: str,
        round_no: int,
        max_rounds: int,
        history: Optional[List[Dict[str, Any]]] = None,
        current_risk: Optional[float] = None,
        memory: Optional[List[Dict[str, Any]]] = None,
        playbook_rules: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        payload = json.dumps(
            {
                "round": round_no,
                "max_rounds": max_rounds,
                "rounds_remaining": max(0, max_rounds - round_no),
                "category": category,
                "clause_text": clause_text[:2500],
                "current_risk_score": current_risk,
                "transcript": [
                    {
                        "round": h.get("round"),
                        "side": h.get("side"),
                        "message": str(h.get("message") or "")[:500],
                        "stance": h.get("stance"),
                    }
                    for h in (history or [])[-6:]
                ],
                "past_negotiation_memory": [
                    {
                        "summary": str(m.get("text") or "")[:300],
                        "outcome": m.get("outcome"),
                        "similarity": m.get("score"),
                    }
                    for m in (memory or [])[:3]
                ],
                "playbook_rules": (playbook_rules or [])[:5],
            },
            ensure_ascii=False,
        )
        result = self.run_json(payload, fallback=None)

        if not isinstance(result, dict) or not result.get("message"):
            return {
                "message": (
                    "No further movement available from this side in this round."
                ),
                "stance": "escalate",
                "proposed_language": clause_text,
                "concession": "none",
                "rationale": "Negotiator produced no usable response.",
                "projected_risk_score": current_risk or 50.0,
                "confidence": 0.3,
                "method": "fallback",
            }

        stance = str(result.get("stance") or "counter").lower()
        if stance not in ("counter", "accept", "reject", "escalate"):
            stance = "counter"

        return {
            "message": str(result.get("message") or "")[:1500],
            "stance": stance,
            "proposed_language": str(result.get("proposed_language") or "")[:4000],
            "concession": str(result.get("concession") or "")[:400],
            "rationale": str(result.get("rationale") or "")[:600],
            "projected_risk_score": round(
                clamp(result.get("projected_risk_score"), 0, 100, current_risk or 50.0), 1
            ),
            "confidence": round(clamp(result.get("confidence"), 0.0, 1.0, 0.7), 3),
            "method": "llm",
        }

    def build_negotiation_payload(self, **kwargs: Any) -> str:
        """Exposed so the SSE streaming route can reuse identical prompt framing."""
        return json.dumps(kwargs, ensure_ascii=False)


class OrganizationNegotiatorAgent(_NegotiatorAgent):
    """Our side of the table. Protects the organisation."""

    key = "organization_negotiator"
    name = "Organization Agent"
    role = roles.ORG_NEGOTIATOR
    persona = (
        "in-house counsel for our organisation, negotiating on our behalf. You "
        "protect us from uncapped liability, one-sided indemnities and unilateral "
        "rights. You are commercially pragmatic, not obstructive: you concede "
        "low-value points to win the ones that matter, you never re-litigate a point "
        "already conceded, and you move toward closure as rounds run down. You state "
        "positions in contract language, not adjectives."
    )
    instructions = (
        "You represent OUR organisation. Given the clause, the transcript so far and "
        "your remaining rounds, make your next negotiation move. Push for terms that "
        "reduce our risk, but concede where the cost is low in order to close. State "
        "your position as concrete proposed contract language. If the remaining gap "
        "is immaterial, accept. If the counterparty will clearly not move and the "
        "risk is unacceptable, escalate to a human"
    )
    hands_off_to = ["counterparty_negotiator", "escalation", "audit"]
    uses_qdrant = True
    qdrant_purpose = (
        "Negotiation memory: retrieves how comparable clauses were settled "
        "previously, so the agent opens from precedent instead of from scratch."
    )


class CounterpartyNegotiatorAgent(_NegotiatorAgent):
    """The other side of the table. Adversarial, but realistic."""

    key = "counterparty_negotiator"
    name = "Counterparty Agent"
    role = roles.COUNTERPARTY_NEGOTIATOR
    persona = (
        "outside counsel for the counterparty, defending their standard terms. You "
        "are a realistic adversary, not a pushover and not a cartoon villain: you "
        "defend your standard positions with commercial justifications, you have "
        "genuine authority limits you will not cross without escalation, and you "
        "concede gradually when pressed with a credible rationale. You are motivated "
        "to close the deal, but on terms favourable to your client."
    )
    instructions = (
        "You represent the COUNTERPARTY and are defending their standard terms. "
        "Given the clause, the transcript so far and your remaining rounds, make your "
        "next move. Defend your position with commercial reasoning, concede "
        "gradually and only when pressed, and state positions as concrete contract "
        "language. Hold a credible authority limit you will not cross. Accept when "
        "the remaining gap is immaterial to your client"
    )
    hands_off_to = ["organization_negotiator", "escalation", "audit"]
    uses_qdrant = True
    qdrant_purpose = (
        "Negotiation memory: retrieves comparable historical settlements to keep "
        "the adversarial positions realistic rather than arbitrary."
    )


# ─────────────────────────────────────────────────────────────────────────────
# 8. Escalation
# ─────────────────────────────────────────────────────────────────────────────


class EscalationAgent(DharmaAgent):
    """Routes high-risk or deadlocked clauses to the human review queue."""

    key = "escalation"
    name = "Escalation Agent"
    role = roles.ESCALATION_OFFICER
    persona = (
        "a triage officer who decides what a human must see. You are deliberately "
        "conservative: a false escalation costs a reviewer ten minutes, a missed one "
        "costs the company a lawsuit. You state precisely what decision the human "
        "needs to make, so they are not re-reading the whole file."
    )
    instructions = (
        "Decide whether this clause requires human review. Escalate when residual "
        "risk is high or critical, when the negotiation deadlocked without agreement, "
        "when a playbook rule is breached and unresolved, or when agent confidence is "
        "low. Return the decision, a priority, the reason, and the specific decision "
        "the human reviewer must make"
    )
    schema_hint = (
        '{"should_escalate": bool, "priority": "low"|"medium"|"high", '
        '"assigned_role": "REVIEWER"|"ADMIN"|null, "reason": str, '
        '"recommended_action": str, "sla_hours": int|null, "confidence": float 0-1}'
    )
    outputs = "Escalate yes/no + priority + assigned role + required human decision"
    hands_off_to = ["audit"]
    temperature = 0.1

    def triage(
        self,
        clause_text: str,
        category: str,
        risk_score: float,
        risk_level: str,
        deadlocked: bool = False,
        unresolved_rules: Optional[List[str]] = None,
        agent_confidence: float = 1.0,
    ) -> Dict[str, Any]:
        payload = json.dumps(
            {
                "category": category,
                "clause_text": clause_text[:2000],
                "risk_score": risk_score,
                "risk_level": risk_level,
                "deadlocked": deadlocked,
                "unresolved_playbook_rules": unresolved_rules or [],
                "agent_confidence": agent_confidence,
                "high_risk_threshold": settings.risk_high_threshold,
            },
            ensure_ascii=False,
        )
        result = self.run_json(payload, fallback=None)

        # Deterministic policy floor: these conditions escalate regardless of what
        # the model concludes. Safety rules are not the model's call.
        #
        # Low agent confidence only escalates when there is also material risk.
        # On its own it floods the queue with boilerplate — a preamble or a
        # definitions clause is inherently hard to categorise, and escalating
        # those trains reviewers to ignore the queue, which defeats the control.
        low_confidence_matters = (
            agent_confidence < LOW_CONFIDENCE_THRESHOLD
            and risk_score >= settings.risk_medium_threshold
        )
        must_escalate = (
            risk_score >= settings.risk_high_threshold
            or risk_level in (RiskLevel.HIGH.value, RiskLevel.CRITICAL.value)
            or deadlocked
            or bool(unresolved_rules)
            or low_confidence_matters
        )

        if not isinstance(result, dict):
            result = {}

        should = bool(result.get("should_escalate")) or must_escalate
        reasons: List[str] = []
        if risk_score >= settings.risk_high_threshold:
            reasons.append(
                f"risk score {risk_score:.0f} at or above the {settings.risk_high_threshold} threshold"
            )
        if deadlocked:
            reasons.append("negotiation reached the round limit without agreement")
        if unresolved_rules:
            reasons.append(f"{len(unresolved_rules)} playbook rule(s) unresolved")
        if agent_confidence < LOW_CONFIDENCE_THRESHOLD:
            reasons.append(f"agent confidence {agent_confidence:.2f} below threshold")

        policy_priority = (
            "high" if (risk_score >= 85 or deadlocked) else "medium" if should else "low"
        )
        priority = str(result.get("priority") or "").lower()
        if priority not in ("low", "medium", "high"):
            priority = policy_priority
        elif should:
            # An escalated item must never be labelled "low". Where the model
            # under-rates something policy forced up, take the higher priority so
            # the reviewer queue orders correctly.
            rank = {"low": 0, "medium": 1, "high": 2}
            if rank[policy_priority] > rank[priority]:
                priority = policy_priority

        return {
            "should_escalate": should,
            "priority": priority,
            "assigned_role": (result.get("assigned_role") or ("REVIEWER" if should else None)),
            "reason": (
                str(result.get("reason") or "")[:600]
                or ("; ".join(reasons).capitalize() + "." if reasons else "Within delegated authority.")
            ),
            "policy_reasons": reasons,
            "recommended_action": str(result.get("recommended_action") or "")[:600],
            "sla_hours": result.get("sla_hours") if should else None,
            "confidence": round(clamp(result.get("confidence"), 0.0, 1.0, 0.85), 3),
            "forced_by_policy": must_escalate and not bool(result.get("should_escalate")),
        }


# ─────────────────────────────────────────────────────────────────────────────
# 9. Audit
# ─────────────────────────────────────────────────────────────────────────────


class AuditAgent(DharmaAgent):
    """Narrates and records every AI decision and human action."""

    key = "audit"
    name = "Audit Agent"
    role = roles.AUDIT_RECORDER
    persona = (
        "a compliance recorder producing an evidentiary trail. You write neutral, "
        "factual, timestamped entries that a regulator or opposing counsel could "
        "read years later. You never editorialise and never omit an unfavourable "
        "fact."
    )
    instructions = (
        "Write a neutral one-sentence audit summary of the supplied event, naming the "
        "actor, the action, and the object acted upon. Add a short compliance note on "
        "why this entry matters for the record. Do not editorialise"
    )
    schema_hint = (
        '{"summary": str, "compliance_note": str, "confidence": float 0-1}'
    )
    outputs = "Immutable, hash-chained audit entry with a human-readable summary"
    hands_off_to = []
    temperature = 0.0

    def narrate(self, event: Dict[str, Any]) -> Dict[str, Any]:
        payload = json.dumps(event, ensure_ascii=False, default=str)[:3000]
        result = self.run_json(payload, fallback=None)
        if not isinstance(result, dict) or not result.get("summary"):
            actor = event.get("actor") or "system"
            action = event.get("event_type") or "action"
            return {
                "summary": f"{actor} performed {action}.",
                "compliance_note": "Entry recorded append-only and hash-chained.",
                "confidence": 0.6,
                "method": "template-fallback",
            }
        return {
            "summary": str(result.get("summary"))[:400],
            "compliance_note": str(result.get("compliance_note") or "")[:400],
            "confidence": round(clamp(result.get("confidence"), 0.0, 1.0, 0.9), 3),
            "method": "llm",
        }


# ─────────────────────────────────────────────────────────────────────────────
# Supporting agents for the signature features
# ─────────────────────────────────────────────────────────────────────────────


class NegotiationStrategyCoachAgent(DharmaAgent):
    """Feature 3: predicts acceptance probability and the strongest next move."""

    key = "strategy_coach"
    name = "Negotiation Strategy Coach"
    role = roles.STRATEGY_COACH
    persona = (
        "a negotiation strategist who has sat through a thousand deals. You read "
        "leverage honestly, including when we have none. You give one concrete next "
        "move, not a list of options, and you say plainly when the right move is to "
        "stop pushing and close."
    )
    instructions = (
        "Predict the probability from 0 to 100 that the counterparty accepts the "
        "current proposed redline, then recommend the single strongest next move. "
        "Assess leverage on both sides honestly, state the risk of pushing further, "
        "and flag whether walking away is warranted"
    )
    schema_hint = (
        '{"acceptance_probability": int 0-100, "recommended_move": str, '
        '"leverage_assessment": str, "risks_of_pushing": str, '
        '"walk_away_signal": bool, "confidence": float 0-1}'
    )
    outputs = "Acceptance probability 0-100% + recommended next move + leverage read"
    hands_off_to = ["organization_negotiator"]
    uses_qdrant = True
    qdrant_purpose = (
        "Retrieves outcomes of similar past negotiations to ground the acceptance "
        "probability in observed history rather than guesswork."
    )
    temperature = 0.4

    def coach(
        self,
        clause_text: str,
        category: str,
        round_no: int,
        history: Optional[List[Dict[str, Any]]] = None,
        proposed_redline: str = "",
        current_risk: Optional[float] = None,
        memory: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        payload = json.dumps(
            {
                "round": round_no,
                "category": category,
                "clause_text": clause_text[:1500],
                "proposed_redline": proposed_redline[:1500],
                "current_risk_score": current_risk,
                "transcript": [
                    {
                        "side": h.get("side"),
                        "stance": h.get("stance"),
                        "message": str(h.get("message") or "")[:300],
                    }
                    for h in (history or [])[-6:]
                ],
                "similar_past_outcomes": [
                    {"summary": str(m.get("text") or "")[:250], "outcome": m.get("outcome")}
                    for m in (memory or [])[:3]
                ],
            },
            ensure_ascii=False,
        )
        result = self.run_json(payload, fallback=None)
        if not isinstance(result, dict):
            result = {}

        return {
            "acceptance_probability": int(
                clamp(result.get("acceptance_probability"), 0, 100, 50)
            ),
            "recommended_move": str(result.get("recommended_move") or "Hold position and request their rationale in writing.")[:600],
            "leverage_assessment": str(result.get("leverage_assessment") or "Leverage is balanced.")[:500],
            "risks_of_pushing": str(result.get("risks_of_pushing") or "Further rounds risk delaying signature.")[:500],
            "walk_away_signal": bool(result.get("walk_away_signal")),
            "confidence": round(clamp(result.get("confidence"), 0.0, 1.0, 0.7), 3),
        }


class ExecutiveSummaryAgent(DharmaAgent):
    """Feature 5: the one-page plain-English brief."""

    key = "executive_summary"
    name = "Executive AI Summary Agent"
    role = roles.EXECUTIVE_BRIEFER
    persona = (
        "a chief of staff briefing a CEO who has four minutes and no legal training. "
        "You write in plain English with no legalese, you lead with the number that "
        "matters, and you never hedge into uselessness. Every risk you raise comes "
        "with the action that resolves it."
    )
    instructions = (
        "Write a one-page executive brief on this contract for a non-lawyer "
        "executive. Cover the key obligations we are taking on, our financial "
        "exposure, the dates that matter, the renewal position, the top risks, and "
        "the specific actions you recommend. Plain English only — no legalese, no "
        "hedging"
    )
    schema_hint = (
        '{"headline": str, "key_obligations": [str], '
        '"financial_exposure": {"headline_figure": str, "notes": str}, '
        '"deadlines": [str], "renewal_terms": str, '
        '"top_risks": [{"clause": str, "risk": str, "why": str}], '
        '"recommended_actions": [str], "overall_recommendation": str, '
        '"confidence": float 0-1}'
    )
    outputs = "One-page plain-English executive brief, exportable to PDF"
    hands_off_to = []
    temperature = 0.3

    def summarize(
        self, title: str, clauses: List[Dict[str, Any]], contract_risk: Dict[str, Any]
    ) -> Dict[str, Any]:
        payload = json.dumps(
            {
                "title": title,
                "contract_risk": contract_risk,
                "clauses": [
                    {
                        "heading": c.get("heading"),
                        "category": c.get("category"),
                        "risk_level": c.get("risk_level"),
                        "risk_score": c.get("risk_score"),
                        "explanation": str(c.get("explanation") or "")[:300],
                        "text": str(c.get("text") or "")[:600],
                    }
                    for c in clauses[:40]
                ],
            },
            ensure_ascii=False,
        )
        result = self.run_json(payload, fallback=None)
        if not isinstance(result, dict) or not result.get("headline"):
            high = [c for c in clauses if c.get("risk_level") in ("High", "Critical")]
            return {
                "headline": (
                    f"{title}: {len(clauses)} clauses reviewed, {len(high)} high-risk."
                ),
                "key_obligations": ["See clause-level review for obligations."],
                "financial_exposure": {
                    "headline_figure": "Not quantified",
                    "notes": "Automated summary unavailable; review clause detail.",
                },
                "deadlines": [],
                "renewal_terms": "See renewal clause.",
                "top_risks": [
                    {
                        "clause": str(c.get("heading") or c.get("category")),
                        "risk": str(c.get("risk_level")),
                        "why": str(c.get("explanation") or "")[:200],
                    }
                    for c in high[:5]
                ],
                "recommended_actions": ["Route high-risk clauses to human review."],
                "overall_recommendation": "Negotiate then sign" if high else "Approve for signature",
                "confidence": 0.4,
                "method": "template-fallback",
            }

        def _str_list(key: str) -> List[str]:
            value = result.get(key)
            return [str(v)[:300] for v in value][:8] if isinstance(value, list) else []

        exposure = result.get("financial_exposure")
        if not isinstance(exposure, dict):
            exposure = {"headline_figure": str(exposure or "Not quantified"), "notes": ""}

        risks = result.get("top_risks")
        top_risks = []
        if isinstance(risks, list):
            for r in risks[:6]:
                if isinstance(r, dict):
                    top_risks.append(
                        {
                            "clause": str(r.get("clause") or "")[:120],
                            "risk": str(r.get("risk") or "")[:20],
                            "why": str(r.get("why") or "")[:300],
                        }
                    )

        return {
            "headline": str(result.get("headline"))[:400],
            "key_obligations": _str_list("key_obligations"),
            "financial_exposure": {
                "headline_figure": str(exposure.get("headline_figure") or "Not quantified")[:100],
                "notes": str(exposure.get("notes") or "")[:400],
            },
            "deadlines": _str_list("deadlines"),
            "renewal_terms": str(result.get("renewal_terms") or "")[:400],
            "top_risks": top_risks,
            "recommended_actions": _str_list("recommended_actions"),
            "overall_recommendation": str(result.get("overall_recommendation") or "")[:200],
            "confidence": round(clamp(result.get("confidence"), 0.0, 1.0, 0.75), 3),
            "method": "llm",
        }


# ─────────────────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────────────────

AGENT_CLASSES = [
    ContractParsingAgent,
    ClauseClassificationAgent,
    PlaybookValidationAgent,
    RiskAssessmentAgent,
    RedlineAgent,
    OrganizationNegotiatorAgent,
    CounterpartyNegotiatorAgent,
    EscalationAgent,
    AuditAgent,
    NegotiationStrategyCoachAgent,
    ExecutiveSummaryAgent,
]

_INSTANCES: Dict[str, DharmaAgent] = {}


def get_agent(key: str) -> DharmaAgent:
    """Return the shared singleton for an agent key."""
    if key not in _INSTANCES:
        for cls in AGENT_CLASSES:
            if cls.key == key:
                _INSTANCES[key] = cls()
                break
        else:
            raise KeyError(f"Unknown agent: {key}")
    return _INSTANCES[key]


def agent_roster() -> List[Dict[str, Any]]:
    """Payload for `GET /api/agents` — powers the Settings page agent table."""
    return [cls.card().__dict__ for cls in AGENT_CLASSES]
