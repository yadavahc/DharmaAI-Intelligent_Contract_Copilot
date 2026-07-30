"""Canonical Lyzr `Agent.role` strings.

Centralised because the role is not just a label: Lyzr injects it into every
system prompt, demo mode dispatches on it, and the Audit Agent keys records by
it. One typo would silently split an agent's audit trail in two.
"""

CONTRACT_PARSER = "Contract Parsing Specialist"
CLAUSE_CLASSIFIER = "Clause Classification Attorney"
PLAYBOOK_VALIDATOR = "Playbook Compliance Officer"
RISK_ASSESSOR = "Contract Risk Analyst"
REDLINE_DRAFTER = "Redline Drafting Attorney"
ORG_NEGOTIATOR = "Organization Negotiator"
COUNTERPARTY_NEGOTIATOR = "Counterparty Negotiator"
ESCALATION_OFFICER = "Escalation Triage Officer"
AUDIT_RECORDER = "Audit and Compliance Recorder"

# Supporting agents behind the five signature features.
STRATEGY_COACH = "Negotiation Strategy Coach"
EXECUTIVE_BRIEFER = "Executive Briefing Analyst"

ALL_ROLES = [
    CONTRACT_PARSER,
    CLAUSE_CLASSIFIER,
    PLAYBOOK_VALIDATOR,
    RISK_ASSESSOR,
    REDLINE_DRAFTER,
    ORG_NEGOTIATOR,
    COUNTERPARTY_NEGOTIATOR,
    ESCALATION_OFFICER,
    AUDIT_RECORDER,
    STRATEGY_COACH,
    EXECUTIVE_BRIEFER,
]
