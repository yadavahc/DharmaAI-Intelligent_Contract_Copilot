"""
Deterministic agent output for demo mode (`DHARMA_DEMO_MODE=true`, or no API key).

Why this exists: a hackathon demo that dies because of a rate limit, an expired
key, or conference wifi is a lost demo. In demo mode every agent still runs
through the real Lyzr `Task`/`LinearSyncPipeline` machinery — only the final
network hop is replaced. The orchestration being demonstrated is genuine; just
the token source is local. The Playwright e2e test runs in this mode for the
same reason.

Dispatch works by parsing the Lyzr-assembled system prompt
(`"In your role as {role}, you embody a persona defined by {persona}."`) to
recover the calling agent's role, then deriving a response from the real clause
text using `heuristics.py`. Output is therefore input-sensitive and plausible,
not a fixed lorem-ipsum string.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, List, Optional

from app.agents import roles
from app.agents.heuristics import (
    classify_clause_heuristic,
    extract_durations_days,
    max_money,
    score_clause_heuristic,
)

_ROLE_RE = re.compile(r"In your role as (?P<role>.+?), you embody a persona")
_INPUT_RE = re.compile(r"\bInput:\s*(?P<payload>.*)\Z", re.DOTALL)


def _role_of(system_persona: str) -> str:
    m = _ROLE_RE.search(system_persona or "")
    return m.group("role").strip() if m else ""


def _payload_of(prompt: str) -> str:
    m = _INPUT_RE.search(prompt or "")
    payload = (m.group("payload") if m else (prompt or "")).strip()
    # A task with no upstream output can contribute a literal "None" or an empty
    # slot before the real payload; strip that noise before parsing.
    return re.sub(r"^(?:None\s*)+", "", payload).strip()


def _as_json(payload: str) -> Optional[Dict[str, Any]]:
    """Parse the agent payload, tolerating text around the JSON object."""
    if not payload:
        return None
    candidates = [payload]
    start, end = payload.find("{"), payload.rfind("}")
    if start != -1 and end > start:
        candidates.append(payload[start : end + 1])
    for cand in candidates:
        try:
            data = json.loads(cand)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict):
            return data
    return None


def _stable_unit(seed: str) -> float:
    """Deterministic pseudo-random in [0,1) from a seed — same input, same demo."""
    digest = hashlib.sha256(seed.encode("utf-8", "ignore")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def synthesize_demo_response(system_persona: str, prompt: str) -> str:
    role = _role_of(system_persona)
    payload = _payload_of(prompt)
    data = _as_json(payload)

    if role == roles.CLAUSE_CLASSIFIER:
        return _demo_classification(payload, data)
    if role == roles.RISK_ASSESSOR:
        return _demo_risk(payload, data)
    if role == roles.PLAYBOOK_VALIDATOR:
        return _demo_playbook(payload, data)
    if role == roles.REDLINE_DRAFTER:
        return _demo_redline(payload, data)
    if role in (roles.ORG_NEGOTIATOR, roles.COUNTERPARTY_NEGOTIATOR):
        return _demo_negotiation(role, payload, data)
    if role == roles.ESCALATION_OFFICER:
        return _demo_escalation(payload, data)
    if role == roles.AUDIT_RECORDER:
        return _demo_audit(payload, data)
    if role == roles.STRATEGY_COACH:
        return _demo_coach(payload, data)
    if role == roles.EXECUTIVE_BRIEFER:
        return _demo_executive(payload, data)
    if role == roles.CONTRACT_PARSER:
        return _demo_parser(payload, data)

    return json.dumps(
        {
            "note": "demo mode: no fixture registered for this role",
            "role": role or "unknown",
        }
    )


# ─────────────────────────────────────────────────────────────────────────────


def _clause_text(payload: str, data: Optional[Dict[str, Any]]) -> str:
    if data:
        for key in ("clause_text", "text", "original", "clause"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return payload


def _demo_classification(payload: str, data: Optional[Dict[str, Any]]) -> str:
    text = _clause_text(payload, data)
    result = classify_clause_heuristic(text)
    return json.dumps(
        {
            "category": result.category,
            "confidence": round(result.confidence, 2),
            "rationale": (
                f"Language signals ({', '.join(result.signals[:3]) or 'structural position'}) "
                f"identify this as a {result.category} provision."
            ),
            "alternatives": result.alternatives[:2],
            "key_terms": result.signals[:5],
        }
    )


def _demo_risk(payload: str, data: Optional[Dict[str, Any]]) -> str:
    text = _clause_text(payload, data)
    category = (data or {}).get("category") or classify_clause_heuristic(text).category
    rules = (data or {}).get("playbook_rules") or []
    result = score_clause_heuristic(text, category, rules)

    amount = max_money(text)
    exposure = f"${amount:,.0f}" if amount else "not quantified in this clause"
    suggested = _suggested_fix(category, result.level)

    return json.dumps(
        {
            "risk_score": round(result.score, 1),
            "risk_level": result.level,
            "explanation": result.rationale,
            "suggested_fix": suggested,
            "financial_exposure": exposure,
            "triggered_rule_ids": result.triggered_rule_ids,
            "findings": [f.detail for f in result.findings][:5],
            "confidence": 0.82,
        }
    )


def _suggested_fix(category: str, level: str) -> str:
    fixes = {
        "Liability": "Cap aggregate liability at 12 months of fees paid and exclude consequential damages for both parties.",
        "Indemnification": "Narrow the indemnity to third-party IP and confidentiality claims, and make it mutual.",
        "Payment": "Move to Net 30 from invoice receipt and cap late interest at 1% per month.",
        "Termination": "Require 30 days' prior written notice with a 15-day cure period before termination.",
        "IP": "Retain ownership of pre-existing IP and grant only a non-exclusive licence for the term.",
        "Confidentiality": "Make confidentiality obligations mutual with a 3-year survival period.",
        "Data Privacy": "Add a DPA with breach notification within 72 hours and sub-processor consent rights.",
        "Warranty": "Add a 90-day services warranty and remove the blanket disclaimer.",
        "Renewal": "Require affirmative written opt-in for renewal, or 60 days' notice of non-renewal.",
        "Non-Compete": "Limit scope to the named field of use and reduce duration to 12 months.",
    }
    default = "Introduce reciprocal obligations and a defined notice period before this clause can be invoked."
    fix = fixes.get(category, default)
    if level in ("Low",):
        return f"Acceptable as drafted; optional improvement — {fix[0].lower() + fix[1:]}"
    return fix


def _demo_playbook(payload: str, data: Optional[Dict[str, Any]]) -> str:
    text = _clause_text(payload, data)
    category = (data or {}).get("category") or classify_clause_heuristic(text).category
    rules: List[Dict[str, Any]] = (data or {}).get("playbook_rules") or []
    result = score_clause_heuristic(text, category, rules)
    violated = [f for f in result.findings if f.source == "playbook"]

    return json.dumps(
        {
            "compliant": not violated,
            "violations": [
                {
                    "rule_id": f.rule_id,
                    "detail": f.detail,
                    "severity": "High" if f.points >= 25 else "Medium",
                }
                for f in violated
            ],
            "matched_rule_ids": [r.get("id") for r in rules][:5],
            "assessment": (
                f"Clause satisfies all {len(rules)} retrieved playbook rules."
                if not violated
                else f"Clause breaches {len(violated)} of {len(rules)} retrieved playbook rules."
            ),
            "confidence": 0.85,
        }
    )


def _demo_redline(payload: str, data: Optional[Dict[str, Any]]) -> str:
    text = _clause_text(payload, data)
    category = (data or {}).get("category") or classify_clause_heuristic(text).category
    amount = max_money(text)

    suggested = text
    # Make a visible, category-appropriate edit so the diff view has real content.
    if category == "Liability" and amount:
        suggested = re.sub(
            r"(unlimited liability|shall have no limitation on liability)",
            "aggregate liability capped at the fees paid in the preceding twelve (12) months",
            text,
            flags=re.IGNORECASE,
        )
        if suggested == text:
            suggested = (
                text.rstrip(". ")
                + ". Notwithstanding the foregoing, each party's aggregate liability "
                "under this Agreement shall not exceed the total fees paid in the "
                "twelve (12) months preceding the claim, and neither party shall be "
                "liable for consequential or punitive damages."
            )
    elif category == "Payment":
        suggested = re.sub(r"net\s*(60|90|120)", "Net 30", text, flags=re.IGNORECASE)
        if suggested == text:
            suggested = text.rstrip(". ") + ". Payment shall be due Net 30 from receipt of a valid invoice."
    elif category == "Termination":
        suggested = re.sub(
            r"without (?:prior )?(?:written )?notice",
            "upon thirty (30) days' prior written notice and a fifteen (15) day cure period",
            text,
            flags=re.IGNORECASE,
        )
        if suggested == text:
            suggested = text.rstrip(". ") + ". Either party may terminate for material breach upon thirty (30) days' prior written notice and opportunity to cure."
    elif category == "Renewal":
        suggested = re.sub(
            r"automatically renew(?:s|ed)?",
            "renew only upon the Customer's affirmative written consent",
            text,
            flags=re.IGNORECASE,
        )
    else:
        suggested = (
            text.rstrip(". ")
            + ". The foregoing obligations shall apply mutually to both parties, "
            "and any exercise of rights hereunder requires reasonable prior written notice."
        )

    return json.dumps(
        {
            "original": text,
            "suggested": suggested,
            "reason": _suggested_fix(category, (data or {}).get("risk_level") or "High"),
            "change_summary": f"Rebalanced the {category} provision toward market-standard terms.",
            "materiality": "high" if category in ("Liability", "Indemnification", "IP") else "medium",
            "confidence": 0.79,
        }
    )


_ORG_MOVES = [
    "We cannot accept uncapped exposure. We propose aggregate liability capped at twelve (12) months of fees, with the standard carve-outs for wilful misconduct and IP infringement.",
    "Understood on the carve-outs, but the cap must be mutual. We will accept a 12-month cap applying equally to both parties, and we will drop our request to exclude data-breach claims from the cap.",
    "We can live with a 15-month cap if confidentiality breaches sit outside it. That is our final position on quantum; we have moved twice.",
    "To close this out: 15-month cap, mutual, with IP and wilful misconduct carved out. We are prepared to sign on that basis today.",
]

_COUNTERPARTY_MOVES = [
    "Our standard position is no cap on liability for breach of confidentiality, and a cap at total contract value for everything else. We rarely depart from this.",
    "We can consider a cap, but 12 months of fees is below our threshold. We would need 24 months of fees, and data-breach claims must remain uncapped.",
    "We will meet you at 18 months of fees with confidentiality breaches carved out of the cap. We cannot go below 18 without internal escalation.",
    "18 months is where our authority ends. If you require 15, that needs sign-off from our General Counsel — we would rather close at 18 and sign now.",
]


def _demo_negotiation(role: str, payload: str, data: Optional[Dict[str, Any]]) -> str:
    round_no = int((data or {}).get("round") or 1)
    idx = max(0, min(round_no - 1, 3))
    is_org = role == roles.ORG_NEGOTIATOR
    message = (_ORG_MOVES if is_org else _COUNTERPARTY_MOVES)[idx]

    text = _clause_text(payload, data)
    category = (data or {}).get("category") or classify_clause_heuristic(text).category

    # Both sides converge as rounds progress; org concedes less than counterparty.
    base = 74.0 if is_org else 66.0
    proposed_risk = max(28.0, base - (round_no * (7.0 if is_org else 5.0)))

    if round_no >= 4:
        stance = "accept" if is_org else "accept"
    elif round_no == 3:
        stance = "counter"
    else:
        stance = "counter"

    return json.dumps(
        {
            "message": message,
            "stance": stance,
            "proposed_language": (
                "Each party's aggregate liability arising out of or relating to this "
                f"Agreement shall not exceed the fees paid or payable in the "
                f"{'twelve (12)' if is_org else 'eighteen (18)'} months preceding the "
                "claim, excluding liability for wilful misconduct and infringement of "
                "intellectual property rights."
            ),
            "concession": (
                "Dropped the data-breach carve-out request"
                if is_org and round_no >= 2
                else "Reduced cap demand from 24 to 18 months of fees"
                if not is_org and round_no >= 2
                else "Opening position; no concession yet"
            ),
            "rationale": (
                f"Round {round_no}: {'protecting our downside on' if is_org else 'defending our standard position on'} "
                f"the {category} provision."
            ),
            "projected_risk_score": round(proposed_risk, 1),
            "confidence": 0.8,
        }
    )


def _demo_escalation(payload: str, data: Optional[Dict[str, Any]]) -> str:
    text = _clause_text(payload, data)
    score = float((data or {}).get("risk_score") or 0)
    deadlocked = bool((data or {}).get("deadlocked"))
    category = (data or {}).get("category") or classify_clause_heuristic(text).category

    should = deadlocked or score >= 70
    reason_bits: List[str] = []
    if score >= 70:
        reason_bits.append(f"residual risk score {score:.0f} exceeds the escalation threshold")
    if deadlocked:
        reason_bits.append("agents reached the round limit without agreement")
    if not reason_bits:
        reason_bits.append("risk is within delegated authority")

    return json.dumps(
        {
            "should_escalate": should,
            "priority": "high" if score >= 85 or deadlocked else "medium" if should else "low",
            "assigned_role": "REVIEWER" if should else None,
            "reason": "; ".join(reason_bits).capitalize() + ".",
            "recommended_action": (
                f"Human counsel should decide the final {category} position: accept the "
                "counterparty's last offer, hold at ours, or authorise a walk-away."
                if should
                else "No human review required; the agent position may be finalised."
            ),
            "sla_hours": 24 if should else None,
            "confidence": 0.88,
        }
    )


def _demo_audit(payload: str, data: Optional[Dict[str, Any]]) -> str:
    event = (data or {}).get("event_type") or "decision"
    actor = (data or {}).get("actor") or "system"
    return json.dumps(
        {
            "summary": f"Recorded {event} by {actor}.",
            "compliance_note": (
                "Entry is append-only and hash-chained to its predecessor; any "
                "retroactive edit would break chain verification."
            ),
            "risk_to_record": (data or {}).get("risk_level") or "n/a",
            "confidence": 0.95,
        }
    )


def _demo_coach(payload: str, data: Optional[Dict[str, Any]]) -> str:
    round_no = int((data or {}).get("round") or 1)
    text = _clause_text(payload, data)
    seed = f"coach:{round_no}:{text[:80]}"
    # Acceptance probability rises as rounds converge.
    prob = 34 + (round_no * 12) + int(_stable_unit(seed) * 10)
    prob = max(5, min(95, prob))

    moves = [
        "Anchor low and justify with market data — cite the 12-month cap as your standard, not an ask.",
        "Trade a low-cost concession (extend the notice period) for the cap reduction you actually need.",
        "Signal finality: state that this is your last movement on quantum and pair it with a same-day signature offer.",
        "Close now. The gap is within tolerance — take the 18-month cap and bank the IP carve-out.",
    ]
    return json.dumps(
        {
            "acceptance_probability": prob,
            "recommended_move": moves[max(0, min(round_no - 1, 3))],
            "leverage_assessment": (
                "Moderate leverage: you hold the signature date, they hold the standard-terms precedent."
            ),
            "risks_of_pushing": (
                "Pushing below a 15-month cap likely triggers their GC review and adds 1–2 weeks."
            ),
            "walk_away_signal": prob < 25,
            "confidence": 0.76,
        }
    )


def _demo_executive(payload: str, data: Optional[Dict[str, Any]]) -> str:
    title = (data or {}).get("title") or "the agreement"
    clauses = (data or {}).get("clauses") or []
    high = [c for c in clauses if str(c.get("risk_level")) in ("High", "Critical")]
    amounts: List[float] = []
    durations: List[int] = []
    for c in clauses:
        amounts.extend([a for a in (max_money(str(c.get("text") or "")),) if a])
        durations.extend(extract_durations_days(str(c.get("text") or "")))
    exposure = max(amounts) if amounts else None

    return json.dumps(
        {
            "headline": (
                f"{title} is commercially workable but carries "
                f"{len(high)} high-risk provision(s) that need resolution before signature."
            ),
            "key_obligations": [
                "Pay all valid invoices within the stated payment window.",
                "Maintain confidentiality of disclosed information for the stated survival period.",
                "Provide the contracted services at the agreed service levels.",
                "Maintain insurance coverage at the specified limits for the term.",
            ],
            "financial_exposure": {
                "headline_figure": f"${exposure:,.0f}" if exposure else "Not expressly quantified",
                "notes": (
                    "Largest quantified figure found in the clause text; uncapped "
                    "liability language, where present, makes true exposure unbounded."
                ),
            },
            "deadlines": [
                f"{d} days" for d in sorted(set(durations))[:4]
            ] or ["No express deadlines detected"],
            "renewal_terms": (
                "Auto-renewal language detected — diarise the non-renewal notice date."
                if any("renew" in str(c.get("text", "")).lower() for c in clauses)
                else "No automatic renewal detected."
            ),
            "top_risks": [
                {
                    "clause": str(c.get("heading") or c.get("category") or "Clause"),
                    "risk": str(c.get("risk_level")),
                    "why": str(c.get("explanation") or "Elevated risk on review.")[:200],
                }
                for c in high[:5]
            ],
            "recommended_actions": [
                "Cap aggregate liability at 12 months of fees before signature.",
                "Make indemnity and confidentiality obligations mutual.",
                "Confirm the non-renewal notice date is tracked by the contract owner.",
                "Route remaining high-risk clauses through human reviewer approval.",
            ],
            "overall_recommendation": (
                "Negotiate then sign" if high else "Approve for signature"
            ),
            "confidence": 0.81,
        }
    )


def _demo_parser(payload: str, data: Optional[Dict[str, Any]]) -> str:
    text = _clause_text(payload, data)
    return json.dumps(
        {
            "title": (data or {}).get("filename") or "Commercial Agreement",
            "parties": ["Acme Corporation (Customer)", "Vendor Industries Ltd (Supplier)"],
            "effective_date": "as stated in the preamble",
            "governing_law": "Delaware" if "delaware" in text.lower() else "as stated in the governing law clause",
            "term": "as stated in the term clause",
            "document_type": "Master Services Agreement",
            "confidence": 0.84,
        }
    )
