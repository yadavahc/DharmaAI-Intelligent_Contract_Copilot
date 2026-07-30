"""
Seed data: the default playbook, precedent library, and a sample contract.

A contract-review demo is only meaningful if there is a playbook to review
against and precedent to recall, so this runs at startup when the tables are
empty. Rules are written to exercise every `rule_type` the risk engine supports
(monetary threshold, duration threshold, forbidden language, required language),
including the brief's own example: liability over $100K is High Risk.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from sqlalchemy import func, select

from app.db import PlaybookRule, session_scope
from app.domain import ClauseCategory

logger = logging.getLogger(__name__)


DEFAULT_PLAYBOOK: List[Dict[str, Any]] = [
    {
        "id": "PB-LIAB-001",
        "title": "Liability exposure above $100,000 is High Risk",
        "category": ClauseCategory.LIABILITY.value,
        "rule_type": "monetary_threshold",
        "operator": "gt",
        "threshold": 100000,
        "severity": "High",
        "risk_points": 30,
        "keywords": ["liability", "aggregate liability", "damages"],
        "guidance": (
            "Any clause exposing the organisation to more than $100,000 must be "
            "escalated. Aggregate liability should be capped at the fees paid in "
            "the preceding twelve (12) months."
        ),
        "preferred_language": (
            "Each party's aggregate liability arising out of or relating to this "
            "Agreement shall not exceed the total fees paid or payable in the twelve "
            "(12) months preceding the event giving rise to the claim, excluding "
            "liability for wilful misconduct, fraud, or infringement of intellectual "
            "property rights."
        ),
    },
    {
        "id": "PB-LIAB-002",
        "title": "Uncapped or unlimited liability is prohibited",
        "category": ClauseCategory.LIABILITY.value,
        "rule_type": "forbidden_language",
        "operator": "",
        "threshold": None,
        "severity": "High",
        "risk_points": 40,
        "keywords": [
            "unlimited liability",
            "no cap on liability",
            "no limitation on liability",
            "without limitation of liability",
        ],
        "guidance": "Unlimited liability is never acceptable without General Counsel sign-off.",
        "preferred_language": (
            "In no event shall either party's aggregate liability exceed the fees paid "
            "in the preceding twelve (12) months."
        ),
    },
    {
        "id": "PB-LIAB-003",
        "title": "Consequential damages must be mutually excluded",
        "category": ClauseCategory.LIABILITY.value,
        "rule_type": "required_language",
        "operator": "",
        "threshold": None,
        "severity": "Medium",
        "risk_points": 18,
        "keywords": ["consequential", "indirect", "punitive"],
        "guidance": (
            "Liability clauses must exclude consequential, indirect and punitive "
            "damages for both parties."
        ),
        "preferred_language": (
            "Neither party shall be liable for any indirect, incidental, "
            "consequential, special or punitive damages."
        ),
    },
    {
        "id": "PB-PAY-001",
        "title": "Payment terms beyond Net 30 require CFO approval",
        "category": ClauseCategory.PAYMENT.value,
        "rule_type": "forbidden_language",
        "operator": "",
        "threshold": None,
        "severity": "Medium",
        "risk_points": 18,
        "keywords": ["net 45", "net 60", "net 90", "net 120"],
        "guidance": "Standard payment terms are Net 30 from receipt of a valid invoice.",
        "preferred_language": (
            "Customer shall pay all undisputed invoices within thirty (30) days of "
            "receipt of a valid invoice."
        ),
    },
    {
        "id": "PB-PAY-002",
        "title": "Contract value above $250,000 requires executive sign-off",
        "category": ClauseCategory.PAYMENT.value,
        "rule_type": "monetary_threshold",
        "operator": "gt",
        "threshold": 250000,
        "severity": "High",
        "risk_points": 25,
        "keywords": ["fees", "purchase price", "total contract value"],
        "guidance": "Commitments above $250,000 require VP Finance approval before signature.",
        "preferred_language": "",
    },
    {
        "id": "PB-TERM-001",
        "title": "Termination requires at least 30 days' written notice",
        "category": ClauseCategory.TERMINATION.value,
        "rule_type": "required_language",
        "operator": "",
        "threshold": None,
        "severity": "High",
        "risk_points": 25,
        "keywords": ["written notice", "notice period", "cure period"],
        "guidance": (
            "No counterparty may terminate without at least 30 days' prior written "
            "notice and a 15-day cure period for remediable breaches."
        ),
        "preferred_language": (
            "Either party may terminate this Agreement for material breach upon thirty "
            "(30) days' prior written notice, provided the breaching party has failed "
            "to cure such breach within fifteen (15) days of such notice."
        ),
    },
    {
        "id": "PB-TERM-002",
        "title": "Notice periods longer than 180 days are excessive",
        "category": ClauseCategory.TERMINATION.value,
        "rule_type": "duration_threshold",
        "operator": "gt",
        "threshold": 180,
        "severity": "Medium",
        "risk_points": 15,
        "keywords": ["notice", "days", "months"],
        "guidance": "Lock-in beyond 180 days materially limits commercial flexibility.",
        "preferred_language": "",
    },
    {
        "id": "PB-IP-001",
        "title": "Pre-existing IP ownership must be retained",
        "category": ClauseCategory.IP.value,
        "rule_type": "forbidden_language",
        "operator": "",
        "threshold": None,
        "severity": "High",
        "risk_points": 35,
        "keywords": [
            "assigns all right, title, and interest",
            "assigns all right",
            "work made for hire",
            "perpetual, irrevocable",
        ],
        "guidance": (
            "We never assign ownership of pre-existing intellectual property. A "
            "non-exclusive licence for the term is the maximum acceptable grant."
        ),
        "preferred_language": (
            "Each party retains all right, title and interest in its pre-existing "
            "intellectual property. Supplier grants Customer a non-exclusive, "
            "non-transferable licence to use the Deliverables for the term."
        ),
    },
    {
        "id": "PB-CONF-001",
        "title": "Confidentiality obligations must be mutual",
        "category": ClauseCategory.CONFIDENTIALITY.value,
        "rule_type": "required_language",
        "operator": "",
        "threshold": None,
        "severity": "Medium",
        "risk_points": 18,
        "keywords": ["each party", "mutual", "both parties", "receiving party"],
        "guidance": "One-way confidentiality in a commercial agreement is not acceptable.",
        "preferred_language": (
            "Each party shall hold the other's Confidential Information in confidence "
            "for a period of three (3) years following disclosure."
        ),
    },
    {
        "id": "PB-DATA-001",
        "title": "Personal data processing requires a DPA and 72-hour breach notice",
        "category": ClauseCategory.DATA_PRIVACY.value,
        "rule_type": "required_language",
        "operator": "",
        "threshold": None,
        "severity": "High",
        "risk_points": 30,
        "keywords": ["data processing agreement", "dpa", "72 hours", "breach notification"],
        "guidance": (
            "Any clause involving personal data must reference a DPA and require "
            "breach notification within 72 hours."
        ),
        "preferred_language": (
            "Supplier shall notify Customer without undue delay and in any event "
            "within seventy-two (72) hours of becoming aware of a Personal Data Breach."
        ),
    },
    {
        "id": "PB-RENEW-001",
        "title": "Automatic renewal without opt-in is prohibited",
        "category": ClauseCategory.RENEWAL.value,
        "rule_type": "forbidden_language",
        "operator": "",
        "threshold": None,
        "severity": "Medium",
        "risk_points": 20,
        "keywords": ["automatically renew", "auto-renew", "evergreen", "successive terms"],
        "guidance": "Renewal must require affirmative written consent, not silence.",
        "preferred_language": (
            "This Agreement shall renew for successive twelve (12) month terms only "
            "upon Customer's affirmative written consent."
        ),
    },
    {
        "id": "PB-INDEM-001",
        "title": "Indemnities must be mutual and scope-limited",
        "category": ClauseCategory.INDEMNIFICATION.value,
        "rule_type": "forbidden_language",
        "operator": "",
        "threshold": None,
        "severity": "High",
        "risk_points": 30,
        "keywords": ["any and all claims", "hold harmless from any", "all losses whatsoever"],
        "guidance": (
            "Indemnities must be limited to third-party claims for IP infringement, "
            "confidentiality breach, and wilful misconduct."
        ),
        "preferred_language": (
            "Each party shall indemnify the other against third-party claims arising "
            "from its breach of confidentiality obligations or infringement of "
            "intellectual property rights."
        ),
    },
    {
        "id": "PB-GLOBAL-001",
        "title": "Unilateral amendment rights are prohibited",
        "category": "*",
        "rule_type": "forbidden_language",
        "operator": "",
        "threshold": None,
        "severity": "High",
        "risk_points": 28,
        "keywords": [
            "unilaterally amend",
            "unilaterally modify",
            "at its sole discretion may change",
            "may modify these terms at any time",
        ],
        "guidance": "No counterparty may change contract terms without our written consent.",
        "preferred_language": (
            "This Agreement may be amended only by a written instrument signed by "
            "authorised representatives of both parties."
        ),
    },
    {
        "id": "PB-GOVLAW-001",
        "title": "Governing law must be a recognised commercial jurisdiction",
        # Scoped to Governing Law, not global: a required-language rule applies
        # only within the clause type it governs.
        "category": ClauseCategory.GOVERNING_LAW.value,
        "rule_type": "required_language",
        "operator": "",
        "threshold": None,
        "severity": "Low",
        "risk_points": 10,
        "keywords": ["delaware", "new york", "england and wales", "singapore"],
        "guidance": "Prefer Delaware, New York, England & Wales, or Singapore.",
        "preferred_language": (
            "This Agreement shall be governed by the laws of the State of Delaware, "
            "without regard to its conflict of laws principles."
        ),
    },
]


# Approved wording that Precedent Recall retrieves as "recommended language".
DEFAULT_PRECEDENTS: List[Dict[str, Any]] = [
    {
        "category": ClauseCategory.LIABILITY.value,
        "contract_title": "Globex Master Services Agreement (executed)",
        "text": (
            "Each party's aggregate liability arising out of or relating to this "
            "Agreement shall not exceed the total fees paid or payable in the twelve "
            "(12) months preceding the event giving rise to the claim. Neither party "
            "shall be liable for indirect, incidental, consequential or punitive "
            "damages. The foregoing limitations shall not apply to liability for "
            "wilful misconduct, fraud, or infringement of intellectual property rights."
        ),
        "risk_level": "Low",
        "notes": "Negotiated cap accepted by counterparty after two rounds.",
    },
    {
        "category": ClauseCategory.PAYMENT.value,
        "contract_title": "Initech Services Agreement (executed)",
        "text": (
            "Customer shall pay all undisputed invoices within thirty (30) days of "
            "receipt of a valid invoice. Disputed amounts shall be notified within "
            "fifteen (15) days and withheld pending resolution. Late payments accrue "
            "interest at the lesser of 1% per month or the maximum permitted by law."
        ),
        "risk_level": "Low",
        "notes": "Standard Net 30 with dispute carve-out.",
    },
    {
        "category": ClauseCategory.TERMINATION.value,
        "contract_title": "Stark Industries MSA (executed)",
        "text": (
            "Either party may terminate this Agreement for material breach upon thirty "
            "(30) days' prior written notice, provided the breaching party has failed "
            "to cure such breach within fifteen (15) days of receipt of such notice. "
            "Customer may terminate for convenience upon sixty (60) days' written "
            "notice with a pro-rata refund of prepaid fees."
        ),
        "risk_level": "Low",
        "notes": "Mutual termination with cure period and pro-rata refund.",
    },
    {
        "category": ClauseCategory.IP.value,
        "contract_title": "Wayne Enterprises Development Agreement (executed)",
        "text": (
            "Each party retains all right, title and interest in and to its "
            "pre-existing intellectual property. Supplier hereby grants Customer a "
            "non-exclusive, worldwide, royalty-free licence to use the Deliverables "
            "for its internal business purposes for the term of this Agreement."
        ),
        "risk_level": "Low",
        "notes": "Licence rather than assignment; approved by IP counsel.",
    },
    {
        "category": ClauseCategory.CONFIDENTIALITY.value,
        "contract_title": "Umbrella Mutual NDA (executed)",
        "text": (
            "Each party shall hold the other party's Confidential Information in "
            "strict confidence and shall not disclose it to any third party without "
            "prior written consent, for a period of three (3) years from the date of "
            "disclosure. These obligations shall not apply to information that is "
            "publicly available through no fault of the receiving party."
        ),
        "risk_level": "Low",
        "notes": "Mutual, 3-year survival, standard carve-outs.",
    },
    {
        "category": ClauseCategory.DATA_PRIVACY.value,
        "contract_title": "Cyberdyne Data Processing Addendum (executed)",
        "text": (
            "Supplier shall process Personal Data only on Customer's documented "
            "instructions and in accordance with the Data Processing Agreement "
            "attached as Exhibit C. Supplier shall notify Customer without undue delay "
            "and in any event within seventy-two (72) hours of becoming aware of a "
            "Personal Data Breach, and shall not engage any sub-processor without "
            "Customer's prior written consent."
        ),
        "risk_level": "Low",
        "notes": "GDPR-aligned with 72-hour notification and sub-processor consent.",
    },
    {
        "category": ClauseCategory.INDEMNIFICATION.value,
        "contract_title": "Soylent Supply Agreement (executed)",
        "text": (
            "Each party shall defend, indemnify and hold harmless the other party "
            "against third-party claims to the extent arising from the indemnifying "
            "party's breach of its confidentiality obligations, infringement of "
            "intellectual property rights, or wilful misconduct. The indemnified party "
            "shall promptly notify the indemnifying party and reasonably cooperate in "
            "the defence."
        ),
        "risk_level": "Low",
        "notes": "Mutual and scope-limited to three enumerated categories.",
    },
]


SAMPLE_CONTRACT_TEXT = """MASTER SERVICES AGREEMENT

This Master Services Agreement ("Agreement") is entered into as of 1 March 2026 between Acme Corporation, a Delaware corporation ("Customer"), and Vendor Industries Ltd, a company incorporated in England and Wales ("Supplier").

1. Definitions. Capitalised terms used in this Agreement shall have the meanings given to them in Schedule A. "Deliverables" means the work product described in each Statement of Work. "Confidential Information" means any non-public information disclosed by one party to the other.

2. Services and Deliverables. Supplier shall provide the services described in each Statement of Work executed by the parties. Supplier may modify the scope of services at its sole discretion upon notice to Customer.

3. Payment Terms. Customer shall pay all invoices Net 90 from the date of invoice. All amounts are non-refundable. Late payments shall accrue interest at 2.5% per month. Total fees under this Agreement shall not exceed $480,000 per annum.

4. Term and Renewal. This Agreement commences on the Effective Date and continues for an initial term of twenty-four (24) months. This Agreement shall automatically renew for successive twelve (12) month terms unless either party provides written notice of non-renewal at least two hundred forty (240) days prior to the end of the then-current term.

5. Termination. Supplier may terminate this Agreement immediately without prior written notice if Customer breaches any provision of this Agreement. Customer may terminate only for material breach after providing ninety (90) days' written notice and an opportunity to cure.

6. Confidentiality. Customer shall hold all Supplier Confidential Information in strict confidence in perpetuity and shall not disclose it to any third party. Supplier shall have no corresponding obligation with respect to Customer information.

7. Intellectual Property. Customer hereby assigns all right, title, and interest in and to any feedback, suggestions, or derivative works arising from the Services to Supplier. Supplier grants Customer a revocable, non-exclusive licence to use the Deliverables, which Supplier may terminate at its sole discretion.

8. Limitation of Liability. Customer shall have unlimited liability for any breach of this Agreement, including consequential, indirect and punitive damages. Supplier's aggregate liability shall not exceed $5,000 in any circumstances. Customer waives any right to a jury trial and any right to participate in a class action.

9. Indemnification. Customer shall defend, indemnify and hold harmless Supplier from any and all claims, losses, damages and expenses whatsoever arising in connection with this Agreement, regardless of cause. Supplier provides no indemnity to Customer.

10. Data Protection. Supplier may process Customer personal data for any purpose it deems appropriate and may engage sub-processors without notice. Supplier shall notify Customer of a data breach within a reasonable period.

11. Warranties. The services are provided "AS IS" without any warranty of any kind. Supplier expressly disclaims all warranties, including any implied warranty of merchantability or fitness for a particular purpose.

12. Insurance. Supplier shall maintain commercial general liability insurance with limits of not less than $1,000,000 per occurrence throughout the term.

13. Assignment. Customer may not assign this Agreement without Supplier's prior written consent. Supplier may assign this Agreement freely, including upon a change of control, without notice to Customer.

14. Amendment. Supplier may unilaterally amend the terms of this Agreement at any time by posting updated terms to its website. Continued use of the Services constitutes acceptance.

15. Governing Law and Disputes. This Agreement shall be governed by the laws of the State of Delaware. All disputes shall be resolved by binding arbitration in London, England, and each party waives any right to a jury trial.

16. Audit Rights. Customer shall have no right to audit or inspect Supplier's books, records, or facilities at any time.
"""


def seed_playbook(force: bool = False) -> Dict[str, Any]:
    """Insert the default playbook if the table is empty (or `force`)."""
    from app.services.qdrant_store import index_playbook_rules

    with session_scope() as session:
        existing = int(
            session.execute(select(func.count()).select_from(PlaybookRule)).scalar() or 0
        )
        if existing and not force:
            # Still ensure Qdrant has them: the vector index is not persisted in
            # the in-memory fallback and would otherwise be empty after a restart.
            rules = [
                _rule_to_dict(r)
                for r in session.execute(select(PlaybookRule)).scalars().all()
            ]
            index_playbook_rules(rules)
            return {"created": 0, "existing": existing, "indexed": len(rules)}

        created = 0
        for spec in DEFAULT_PLAYBOOK:
            if session.get(PlaybookRule, spec["id"]) is not None:
                continue
            session.add(
                PlaybookRule(
                    id=spec["id"],
                    title=spec["title"],
                    category=spec["category"],
                    rule_type=spec["rule_type"],
                    operator=spec.get("operator") or "",
                    threshold=spec.get("threshold"),
                    keywords=spec.get("keywords") or [],
                    severity=spec.get("severity") or "Medium",
                    risk_points=int(spec.get("risk_points") or 20),
                    guidance=spec.get("guidance") or "",
                    preferred_language=spec.get("preferred_language") or "",
                    active=True,
                    created_by="system:seed",
                )
            )
            created += 1

    # Index from the database, not from DEFAULT_PLAYBOOK: an admin's custom rules
    # must be embedded too, and on a forced re-index they would otherwise be
    # silently dropped from retrieval.
    active = get_active_rules()
    index_playbook_rules(active)
    logger.info("Seeded %d playbook rules; indexed %d active.", created, len(active))
    return {"created": created, "existing": 0, "indexed": len(active)}


def _rule_to_dict(rule: PlaybookRule) -> Dict[str, Any]:
    return {
        "id": rule.id,
        "title": rule.title,
        "category": rule.category,
        "rule_type": rule.rule_type,
        "operator": rule.operator,
        "threshold": rule.threshold,
        "keywords": rule.keywords or [],
        "severity": rule.severity,
        "risk_points": rule.risk_points,
        "guidance": rule.guidance,
        "preferred_language": rule.preferred_language,
        "active": rule.active,
    }


def seed_precedents() -> Dict[str, Any]:
    """Populate the precedent library that Precedent Recall searches."""
    from app.services.qdrant_store import PRECEDENTS, get_store, index_precedent

    store = get_store()
    if store.count(PRECEDENTS) >= len(DEFAULT_PRECEDENTS):
        return {"created": 0, "existing": store.count(PRECEDENTS)}

    for i, precedent in enumerate(DEFAULT_PRECEDENTS):
        index_precedent(
            precedent["text"],
            precedent["category"],
            contract_title=precedent["contract_title"],
            contract_id=f"seed-precedent-{i}",
            clause_id=f"seed-clause-{i}",
            approved_by="system:seed",
            risk_level=precedent.get("risk_level", "Low"),
            notes=precedent.get("notes", ""),
        )
    logger.info("Seeded %d precedent clauses.", len(DEFAULT_PRECEDENTS))
    return {"created": len(DEFAULT_PRECEDENTS), "existing": 0}


def seed_all() -> Dict[str, Any]:
    """Seed reference data, repairing any collection left in a stale vector space.

    Switching embedding backends (demo mode → live key, or a different embedding
    model) invalidates every stored vector: cosine similarity across two spaces is
    noise, not a weak match. The seeded collections can simply be rebuilt, so they
    are. Clause and negotiation vectors cannot be regenerated from here — those
    need a re-review — so they are reported loudly instead.
    """
    from app.services.qdrant_store import (
        CLAUSES,
        NEGOTIATIONS,
        PLAYBOOK,
        PRECEDENTS,
        check_embedding_consistency,
        get_store,
    )

    consistency = check_embedding_consistency()
    stale = set(consistency["stale"])
    repaired: List[str] = []

    if stale:
        logger.warning(
            "Vector spaces are inconsistent (current: %s). Stale collections: %s",
            consistency["current"],
            ", ".join(sorted(stale)),
        )

    store = get_store()
    for name in (PLAYBOOK, PRECEDENTS):
        if name in stale:
            store.clear(name)
            repaired.append(name)

    result: Dict[str, Any] = {
        "playbook": seed_playbook(force=PLAYBOOK in repaired),
        "precedents": seed_precedents(),
        "embedding_consistency": consistency,
        "repaired": repaired,
    }

    needs_reingest = sorted(stale & {CLAUSES, NEGOTIATIONS})
    if needs_reingest:
        result["needs_reingest"] = needs_reingest
        logger.warning(
            "%s were embedded in a different vector space and cannot be rebuilt "
            "automatically. Re-run the review on affected contracts, or POST "
            "/api/demo/reset, otherwise their similarity scores are meaningless.",
            ", ".join(needs_reingest),
        )

    return result


def get_active_rules() -> List[Dict[str, Any]]:
    with session_scope() as session:
        rows = (
            session.execute(select(PlaybookRule).where(PlaybookRule.active.is_(True)))
            .scalars()
            .all()
        )
        return [_rule_to_dict(r) for r in rows]
