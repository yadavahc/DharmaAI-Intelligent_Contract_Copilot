"""Shared vocabulary: clause taxonomy, risk levels, statuses, roles.

Imported by agents, services and routers so the same strings travel end-to-end
and the frontend can rely on a fixed set.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List


class ClauseCategory(str, Enum):
    PAYMENT = "Payment"
    TERMINATION = "Termination"
    LIABILITY = "Liability"
    INDEMNIFICATION = "Indemnification"
    CONFIDENTIALITY = "Confidentiality"
    IP = "IP"
    DATA_PRIVACY = "Data Privacy"
    WARRANTY = "Warranty"
    GOVERNING_LAW = "Governing Law"
    DISPUTE_RESOLUTION = "Dispute Resolution"
    FORCE_MAJEURE = "Force Majeure"
    ASSIGNMENT = "Assignment"
    RENEWAL = "Renewal"
    SLA = "Service Levels"
    INSURANCE = "Insurance"
    COMPLIANCE = "Compliance"
    NON_COMPETE = "Non-Compete"
    AUDIT_RIGHTS = "Audit Rights"
    DEFINITIONS = "Definitions"
    OTHER = "Other"

    @classmethod
    def values(cls) -> List[str]:
        return [c.value for c in cls]


class RiskLevel(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class ContractStatus(str, Enum):
    UPLOADED = "uploaded"
    PARSING = "parsing"
    CLASSIFYING = "classifying"
    ASSESSING = "assessing"
    READY = "ready"
    NEGOTIATING = "negotiating"
    ESCALATED = "escalated"
    APPROVED = "approved"
    FAILED = "failed"


class NegotiationOutcome(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ESCALATED = "escalated"


class ReviewDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    EDIT = "edit"
    COMMENT = "comment"


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    REVIEWER = "REVIEWER"
    BUSINESS_USER = "BUSINESS_USER"


class ActorType(str, Enum):
    AI_AGENT = "ai_agent"
    HUMAN = "human"
    SYSTEM = "system"


def risk_level_for_score(
    score: float, high_threshold: int = 70, medium_threshold: int = 40
) -> RiskLevel:
    """Single source of truth for score → level. Unit-tested in tests/test_risk_scoring.py."""
    if score >= 90:
        return RiskLevel.CRITICAL
    if score >= high_threshold:
        return RiskLevel.HIGH
    if score >= medium_threshold:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


# Weights used when rolling clause scores up to one contract score. Clauses that
# can sink a deal count for more than boilerplate.
CATEGORY_WEIGHTS: Dict[str, float] = {
    ClauseCategory.LIABILITY.value: 1.6,
    ClauseCategory.INDEMNIFICATION.value: 1.5,
    ClauseCategory.IP.value: 1.4,
    ClauseCategory.DATA_PRIVACY.value: 1.35,
    ClauseCategory.PAYMENT.value: 1.3,
    ClauseCategory.TERMINATION.value: 1.25,
    ClauseCategory.CONFIDENTIALITY.value: 1.15,
    ClauseCategory.NON_COMPETE.value: 1.15,
    ClauseCategory.WARRANTY.value: 1.1,
    ClauseCategory.SLA.value: 1.1,
    ClauseCategory.INSURANCE.value: 1.05,
    ClauseCategory.COMPLIANCE.value: 1.05,
    ClauseCategory.RENEWAL.value: 1.0,
    ClauseCategory.AUDIT_RIGHTS.value: 0.95,
    ClauseCategory.ASSIGNMENT.value: 0.9,
    ClauseCategory.DISPUTE_RESOLUTION.value: 0.9,
    ClauseCategory.GOVERNING_LAW.value: 0.85,
    ClauseCategory.FORCE_MAJEURE.value: 0.8,
    ClauseCategory.DEFINITIONS.value: 0.5,
    ClauseCategory.OTHER.value: 0.7,
}

DEFAULT_CATEGORY_WEIGHT = 1.0


def category_weight(category: str) -> float:
    return CATEGORY_WEIGHTS.get(category, DEFAULT_CATEGORY_WEIGHT)


# Keyword signals per category. Used by the deterministic classifier fallback
# (and demo mode) so classification still works with no LLM available.
CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    ClauseCategory.PAYMENT.value: [
        "payment", "invoice", "net 30", "net 45", "net 60", "net 90", "fees",
        "late fee", "interest", "purchase price", "remit", "billing", "prepaid",
    ],
    ClauseCategory.TERMINATION.value: [
        "terminate", "termination", "for convenience", "for cause", "notice period",
        "wind-down", "expiration", "cancel",
    ],
    ClauseCategory.LIABILITY.value: [
        "liability", "liable", "aggregate liability", "cap on liability",
        "consequential damages", "limitation of liability", "damages",
    ],
    ClauseCategory.INDEMNIFICATION.value: [
        "indemnify", "indemnification", "hold harmless", "defend", "third-party claim",
    ],
    ClauseCategory.CONFIDENTIALITY.value: [
        "confidential", "confidentiality", "non-disclosure", "proprietary information",
        "trade secret",
    ],
    ClauseCategory.IP.value: [
        "intellectual property", "ownership", "work product", "license grant",
        "copyright", "patent", "trademark", "derivative works", "assigns all right",
    ],
    ClauseCategory.DATA_PRIVACY.value: [
        "personal data", "gdpr", "ccpa", "data processing", "data subject",
        "sub-processor", "privacy", "data breach",
    ],
    ClauseCategory.WARRANTY.value: [
        "warrant", "warranty", "as is", "merchantability", "fitness for a particular",
        "disclaimer",
    ],
    ClauseCategory.GOVERNING_LAW.value: [
        "governing law", "governed by the laws", "jurisdiction", "venue",
        "conflict of laws",
    ],
    ClauseCategory.DISPUTE_RESOLUTION.value: [
        "arbitration", "arbitrator", "mediation", "dispute resolution",
        "waiver of jury", "class action",
    ],
    ClauseCategory.FORCE_MAJEURE.value: [
        "force majeure", "acts of god", "beyond the reasonable control",
        "epidemic", "pandemic",
    ],
    ClauseCategory.ASSIGNMENT.value: [
        "assign", "assignment", "successors and assigns", "change of control",
        "transfer this agreement",
    ],
    ClauseCategory.RENEWAL.value: [
        "renew", "renewal", "auto-renew", "automatically renew", "successive terms",
        "evergreen",
    ],
    ClauseCategory.SLA.value: [
        "service level", "uptime", "availability", "response time", "service credit",
        "downtime",
    ],
    ClauseCategory.INSURANCE.value: [
        "insurance", "insurer", "coverage", "certificate of insurance",
        "commercial general liability",
    ],
    ClauseCategory.COMPLIANCE.value: [
        "comply with all applicable", "anti-corruption", "fcpa", "sanctions",
        "export control", "applicable laws",
    ],
    ClauseCategory.NON_COMPETE.value: [
        "non-compete", "noncompetition", "shall not compete", "non-solicit",
        "solicitation of employees",
    ],
    ClauseCategory.AUDIT_RIGHTS.value: [
        "audit", "inspect records", "books and records", "right to examine",
    ],
    ClauseCategory.DEFINITIONS.value: [
        "definitions", "shall mean", "as used in this agreement", "capitalized terms",
    ],
}
