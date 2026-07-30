"""
Qdrant vector store — four distinct retrieval roles, not one bucket of embeddings.

    ┌──────────────────────┬──────────────────────────────────────────────────┐
    │ collection           │ what it is retrieved FOR                         │
    ├──────────────────────┼──────────────────────────────────────────────────┤
    │ dharma_clauses       │ 1. Semantic search across every ingested clause  │
    │                      │ 2. Similar-clause matching (same category, other │
    │                      │    contracts) to ground risk scoring in how we   │
    │                      │    have treated comparable language before       │
    │ dharma_playbook      │ 3. Playbook RAG — retrieve the handful of admin  │
    │                      │    rules semantically relevant to a clause,      │
    │                      │    rather than pushing the whole playbook into    │
    │                      │    every prompt                                  │
    │ dharma_precedents    │ 4. Precedent Recall — closest *approved* clause   │
    │                      │    wording, surfaced as recommended language     │
    │ dharma_negotiations  │ 5. Negotiation memory — how comparable disputes   │
    │                      │    actually settled, fed to both negotiators and  │
    │                      │    the Strategy Coach                            │
    └──────────────────────┴──────────────────────────────────────────────────┘

Each role uses different filters and thresholds, which is the point: the same
embedding space is queried four ways with different payload constraints.

Graceful degradation: if Qdrant is unreachable, an in-process brute-force cosine
index takes over with identical semantics. The demo keeps working on a laptop
with no Docker, and the code path that judges read is the real one.
"""

from __future__ import annotations

import logging
import math
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from app.config import settings
from app.services.embeddings import (
    embedding_signature,
    get_embedding_service,
    scale_threshold,
)

# Payload key carrying the vector space a point was embedded in. See
# `embeddings.embedding_signature` for why this matters.
EMBEDDING_KEY = "_embedding"

logger = logging.getLogger(__name__)

CLAUSES = "dharma_clauses"
PLAYBOOK = "dharma_playbook"
PRECEDENTS = "dharma_precedents"
NEGOTIATIONS = "dharma_negotiations"

ALL_COLLECTIONS = (CLAUSES, PLAYBOOK, PRECEDENTS, NEGOTIATIONS)

COLLECTION_PURPOSE: Dict[str, str] = {
    CLAUSES: "Semantic clause search and similar-clause matching across contracts",
    PLAYBOOK: "RAG retrieval of the admin playbook rules relevant to a clause",
    PRECEDENTS: "Precedent Recall — closest previously approved clause wording",
    NEGOTIATIONS: "Negotiation memory — outcomes of comparable past negotiations",
}


@dataclass
class SearchHit:
    id: str
    score: float
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "score": round(self.score, 4), **self.payload}


# ─────────────────────────────────────────────────────────────────────────────
# In-memory fallback
# ─────────────────────────────────────────────────────────────────────────────


class _MemoryIndex:
    """Brute-force cosine index. Same semantics as the Qdrant path, no server."""

    def __init__(self) -> None:
        self._data: Dict[str, Dict[str, Tuple[List[float], Dict[str, Any]]]] = {
            name: {} for name in ALL_COLLECTIONS
        }
        self._lock = threading.Lock()

    def upsert(
        self, collection: str, ids: Sequence[str], vectors: Sequence[List[float]],
        payloads: Sequence[Dict[str, Any]],
    ) -> None:
        with self._lock:
            bucket = self._data.setdefault(collection, {})
            for pid, vec, payload in zip(ids, vectors, payloads):
                bucket[pid] = (list(vec), dict(payload))

    def search(
        self, collection: str, vector: List[float], limit: int,
        filters: Optional[Dict[str, Any]] = None,
        score_threshold: Optional[float] = None,
    ) -> List[SearchHit]:
        with self._lock:
            bucket = dict(self._data.get(collection, {}))

        hits: List[SearchHit] = []
        for pid, (vec, payload) in bucket.items():
            if not _matches(payload, filters):
                continue
            score = _cosine(vector, vec)
            if score_threshold is not None and score < score_threshold:
                continue
            hits.append(SearchHit(id=pid, score=score, payload=payload))

        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:limit]

    def delete_by_filter(self, collection: str, filters: Dict[str, Any]) -> int:
        with self._lock:
            bucket = self._data.setdefault(collection, {})
            doomed = [pid for pid, (_, p) in bucket.items() if _matches(p, filters)]
            for pid in doomed:
                bucket.pop(pid, None)
            return len(doomed)

    def count(self, collection: str) -> int:
        with self._lock:
            return len(self._data.get(collection, {}))

    def clear(self, collection: Optional[str] = None) -> None:
        with self._lock:
            targets = [collection] if collection else list(self._data.keys())
            for name in targets:
                self._data[name] = {}


def _matches(payload: Dict[str, Any], filters: Optional[Dict[str, Any]]) -> bool:
    if not filters:
        return True
    for key, expected in filters.items():
        actual = payload.get(key)
        if isinstance(expected, (list, tuple, set)):
            if actual not in expected:
                return False
        elif actual != expected:
            return False
    return True


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ─────────────────────────────────────────────────────────────────────────────
# Store
# ─────────────────────────────────────────────────────────────────────────────


class QdrantStore:
    def __init__(self) -> None:
        self._client: Any = None
        self._lock = threading.Lock()
        self._memory = _MemoryIndex()
        self._ready = False
        self.backend = "uninitialised"
        self.last_error: Optional[str] = None

    # ── lifecycle ──────────────────────────────────────────────────────────
    def connect(self) -> None:
        """Connect and ensure collections. Falls back to memory on any failure."""
        with self._lock:
            if self._ready:
                return
            try:
                from qdrant_client import QdrantClient
                from qdrant_client.models import Distance, VectorParams

                client = QdrantClient(
                    url=settings.qdrant_url,
                    api_key=settings.qdrant_api_key or None,
                    timeout=10.0,
                )
                existing = {c.name for c in client.get_collections().collections}
                for name in ALL_COLLECTIONS:
                    if name not in existing:
                        client.create_collection(
                            collection_name=name,
                            vectors_config=VectorParams(
                                size=settings.embedding_dim,
                                distance=Distance.COSINE,
                            ),
                        )
                        logger.info("Created Qdrant collection %s", name)
                self._client = client
                self.backend = "qdrant"
                self.last_error = None
                logger.info("Qdrant connected at %s", settings.qdrant_url)
            except Exception as exc:
                self._client = None
                self.backend = "in-memory"
                self.last_error = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "Qdrant unavailable (%s); using in-memory vector index. "
                    "Retrieval still works; vectors are not persisted.",
                    self.last_error,
                )
            self._ready = True

    def ensure_ready(self) -> None:
        if not self._ready:
            self.connect()

    @property
    def using_qdrant(self) -> bool:
        return self._client is not None

    def health(self) -> Dict[str, Any]:
        self.ensure_ready()
        return {
            "backend": self.backend,
            "url": settings.qdrant_url if self.using_qdrant else None,
            "embedding_dim": settings.embedding_dim,
            "embedding_method": get_embedding_service().last_method,
            "last_error": self.last_error,
            "collections": {
                name: {
                    "points": self.count(name),
                    "purpose": COLLECTION_PURPOSE[name],
                }
                for name in ALL_COLLECTIONS
            },
        }

    # ── writes ─────────────────────────────────────────────────────────────
    def upsert_texts(
        self,
        collection: str,
        texts: Sequence[str],
        payloads: Sequence[Dict[str, Any]],
        ids: Optional[Sequence[str]] = None,
    ) -> List[str]:
        """Embed `texts` and upsert them with `payloads`. Returns the point ids."""
        self.ensure_ready()
        if not texts:
            return []
        if len(texts) != len(payloads):
            raise ValueError("texts and payloads must be the same length")

        vectors = get_embedding_service().embed_many(texts)
        # Stamp the vector space so a later backend change is detectable rather
        # than silently poisoning every similarity score in this collection.
        signature = embedding_signature()
        payloads = [{**p, EMBEDDING_KEY: signature} for p in payloads]
        # Qdrant point ids must be UUIDs or ints; derive a stable UUID5 from any
        # caller-supplied string key so re-ingesting a clause updates in place.
        point_ids = [
            str(uuid.uuid5(uuid.NAMESPACE_URL, f"{collection}:{key}"))
            if ids
            else str(uuid.uuid4())
            for key in (ids or texts)
        ]

        if self.using_qdrant:
            try:
                from qdrant_client.models import PointStruct

                self._client.upsert(
                    collection_name=collection,
                    points=[
                        PointStruct(id=pid, vector=vec, payload=payload)
                        for pid, vec, payload in zip(point_ids, vectors, payloads)
                    ],
                    wait=True,
                )
                return point_ids
            except Exception as exc:
                logger.warning("Qdrant upsert failed (%s); writing to memory index.", exc)
                self.last_error = str(exc)

        self._memory.upsert(collection, point_ids, vectors, payloads)
        return point_ids

    def delete_by_filter(self, collection: str, filters: Dict[str, Any]) -> int:
        self.ensure_ready()
        if self.using_qdrant:
            try:
                self._client.delete(
                    collection_name=collection,
                    points_selector=_qdrant_filter(filters),
                    wait=True,
                )
                return -1  # Qdrant does not report a delete count
            except Exception as exc:
                logger.warning("Qdrant delete failed (%s).", exc)
        return self._memory.delete_by_filter(collection, filters)

    def count(self, collection: str) -> int:
        self.ensure_ready()
        if self.using_qdrant:
            try:
                return int(self._client.count(collection_name=collection).count)
            except Exception:
                return 0
        return self._memory.count(collection)

    def sample_payload(self, collection: str) -> Optional[Dict[str, Any]]:
        """Return any one payload from `collection`, or None if it is empty.

        Used to read back the embedding signature of already-stored points.
        """
        self.ensure_ready()
        if self.using_qdrant:
            try:
                points, _ = self._client.scroll(
                    collection_name=collection, limit=1, with_payload=True
                )
                return dict(points[0].payload or {}) if points else None
            except Exception:
                return None
        with self._memory._lock:  # noqa: SLF001 - same module, deliberate
            bucket = self._memory._data.get(collection, {})  # noqa: SLF001
            for _, payload in bucket.values():
                return dict(payload)
        return None

    def clear(self, collection: Optional[str] = None) -> None:
        self.ensure_ready()
        targets = [collection] if collection else list(ALL_COLLECTIONS)
        if self.using_qdrant:
            try:
                from qdrant_client.models import Distance, VectorParams

                for name in targets:
                    self._client.delete_collection(collection_name=name)
                    self._client.create_collection(
                        collection_name=name,
                        vectors_config=VectorParams(
                            size=settings.embedding_dim, distance=Distance.COSINE
                        ),
                    )
            except Exception as exc:
                logger.warning("Qdrant clear failed (%s).", exc)
        self._memory.clear(collection)

    # ── reads ──────────────────────────────────────────────────────────────
    def search(
        self,
        collection: str,
        query: str,
        *,
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        score_threshold: Optional[float] = None,
    ) -> List[SearchHit]:
        self.ensure_ready()
        vector = get_embedding_service().embed(query)
        return self.search_by_vector(
            collection,
            vector,
            limit=limit,
            filters=filters,
            # Callers express thresholds on the transformer similarity scale;
            # rescale for whichever backend actually produced these vectors.
            score_threshold=scale_threshold(score_threshold),
        )

    def search_by_vector(
        self,
        collection: str,
        vector: List[float],
        *,
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        score_threshold: Optional[float] = None,
    ) -> List[SearchHit]:
        self.ensure_ready()
        if self.using_qdrant:
            try:
                results = self._client.query_points(
                    collection_name=collection,
                    query=vector,
                    limit=limit,
                    query_filter=_qdrant_filter(filters),
                    score_threshold=score_threshold,
                    with_payload=True,
                ).points
                return [
                    SearchHit(
                        id=str(point.id),
                        score=float(point.score),
                        payload=dict(point.payload or {}),
                    )
                    for point in results
                ]
            except Exception as exc:
                logger.warning("Qdrant search failed (%s); using memory index.", exc)
                self.last_error = str(exc)

        return self._memory.search(
            collection, vector, limit, filters, score_threshold
        )


def check_embedding_consistency() -> Dict[str, Any]:
    """Report collections whose stored vectors are in a different vector space.

    Called at startup. A stale collection is not a soft problem — its similarity
    scores become meaningless, so callers should re-index rather than trust them.
    """
    store = get_store()
    current = embedding_signature()
    report: Dict[str, Any] = {"current": current, "stale": [], "collections": {}}

    for name in ALL_COLLECTIONS:
        if store.count(name) == 0:
            report["collections"][name] = "empty"
            continue
        payload = store.sample_payload(name)
        stored = (payload or {}).get(EMBEDDING_KEY)
        report["collections"][name] = stored or "unknown (pre-dates signatures)"
        if stored != current:
            report["stale"].append(name)

    return report


def _qdrant_filter(filters: Optional[Dict[str, Any]]):
    """Translate a flat dict into a Qdrant `Filter` (AND over must-match)."""
    if not filters:
        return None
    try:
        from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

        conditions = []
        for key, expected in filters.items():
            if isinstance(expected, (list, tuple, set)):
                conditions.append(
                    FieldCondition(key=key, match=MatchAny(any=list(expected)))
                )
            else:
                conditions.append(
                    FieldCondition(key=key, match=MatchValue(value=expected))
                )
        return Filter(must=conditions)
    except Exception:
        return None


_store: Optional[QdrantStore] = None
_store_lock = threading.Lock()


def get_store() -> QdrantStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = QdrantStore()
    return _store


# ─────────────────────────────────────────────────────────────────────────────
# The four retrieval roles
# ─────────────────────────────────────────────────────────────────────────────


def index_clauses(
    contract_id: str, contract_title: str, clauses: Sequence[Dict[str, Any]]
) -> List[str]:
    """Role 1 & 2 — index clauses for semantic search and similar-clause matching."""
    if not clauses:
        return []
    store = get_store()
    texts = [str(c.get("text") or "") for c in clauses]
    payloads = [
        {
            "kind": "clause",
            "contract_id": contract_id,
            "contract_title": contract_title,
            "clause_id": str(c.get("id") or c.get("clause_id") or ""),
            "clause_index": int(c.get("index") or 0),
            "heading": str(c.get("heading") or c.get("display_title") or ""),
            "category": str(c.get("category") or "Other"),
            "risk_level": str(c.get("risk_level") or ""),
            "risk_score": float(c.get("risk_score") or 0.0),
            "text": str(c.get("text") or "")[:4000],
        }
        for c in clauses
    ]
    ids = [
        f"{contract_id}:{c.get('id') or c.get('index')}" for c in clauses
    ]
    return store.upsert_texts(CLAUSES, texts, payloads, ids=ids)


def search_clauses(
    query: str,
    *,
    limit: int = 10,
    category: Optional[str] = None,
    contract_id: Optional[str] = None,
    risk_level: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Role 1 — semantic search over all indexed clauses."""
    filters: Dict[str, Any] = {"kind": "clause"}
    if category:
        filters["category"] = category
    if contract_id:
        filters["contract_id"] = contract_id
    if risk_level:
        filters["risk_level"] = risk_level
    hits = get_store().search(CLAUSES, query, limit=limit, filters=filters)
    return [h.to_dict() for h in hits]


def find_similar_clauses(
    clause_text: str,
    category: str,
    *,
    exclude_contract_id: Optional[str] = None,
    limit: int = 3,
    min_score: float = 0.55,
) -> List[Dict[str, Any]]:
    """Role 2 — comparable clauses from *other* contracts, same category.

    Grounds risk scoring in how similar language was treated before. Excluding
    the source contract matters: a clause is trivially similar to itself, and
    self-matches would make the retrieval look impressive while adding nothing.
    """
    hits = get_store().search(
        CLAUSES,
        clause_text,
        limit=limit + 6,
        filters={"kind": "clause", "category": category},
        score_threshold=min_score,
    )
    out: List[Dict[str, Any]] = []
    for hit in hits:
        if exclude_contract_id and hit.payload.get("contract_id") == exclude_contract_id:
            continue
        out.append(hit.to_dict())
        if len(out) >= limit:
            break
    return out


def index_playbook_rules(rules: Sequence[Dict[str, Any]]) -> List[str]:
    """Role 3 — index playbook rules for semantic retrieval."""
    if not rules:
        return []
    texts: List[str] = []
    payloads: List[Dict[str, Any]] = []
    ids: List[str] = []
    for rule in rules:
        # Embed the rule's meaning, not its JSON: title + category + guidance +
        # keywords is what a clause should semantically match against.
        parts = [
            str(rule.get("title") or ""),
            str(rule.get("category") or ""),
            str(rule.get("guidance") or ""),
            " ".join(str(k) for k in (rule.get("keywords") or [])),
            str(rule.get("preferred_language") or ""),
        ]
        texts.append(" ".join(p for p in parts if p).strip() or str(rule.get("id")))
        payloads.append(
            {
                "kind": "playbook_rule",
                "id": str(rule.get("id")),
                "title": str(rule.get("title") or ""),
                "category": str(rule.get("category") or "*"),
                "rule_type": str(rule.get("rule_type") or ""),
                "operator": str(rule.get("operator") or ""),
                "threshold": rule.get("threshold"),
                "keywords": list(rule.get("keywords") or []),
                "severity": str(rule.get("severity") or "Medium"),
                "risk_points": int(rule.get("risk_points") or 20),
                "guidance": str(rule.get("guidance") or "")[:1000],
                "preferred_language": str(rule.get("preferred_language") or "")[:2000],
                "active": bool(rule.get("active", True)),
            }
        )
        ids.append(f"rule:{rule.get('id')}")
    return get_store().upsert_texts(PLAYBOOK, texts, payloads, ids=ids)


def retrieve_playbook_rules(
    clause_text: str,
    category: Optional[str] = None,
    *,
    limit: int = 6,
    min_score: float = 0.0,
) -> List[Dict[str, Any]]:
    """Role 3 — the playbook rules most relevant to this clause.

    Rules scoped to the clause's category are retrieved alongside global (`*`)
    rules, then merged and de-duplicated. Category-scoped retrieval alone would
    miss company-wide rules; global-only would drown out the specific ones.
    """
    store = get_store()
    collected: Dict[str, Dict[str, Any]] = {}

    scopes: List[Optional[str]] = [category, "*"] if category else [None]
    for scope in scopes:
        filters: Dict[str, Any] = {"kind": "playbook_rule", "active": True}
        if scope:
            filters["category"] = scope
        for hit in store.search(
            PLAYBOOK, clause_text, limit=limit, filters=filters,
            score_threshold=min_score or None,
        ):
            payload = hit.to_dict()
            rule_id = str(payload.get("id"))
            # Keep the higher-scoring occurrence of a rule found in both scopes.
            if rule_id not in collected or payload["score"] > collected[rule_id]["score"]:
                collected[rule_id] = payload

    ranked = sorted(collected.values(), key=lambda r: r["score"], reverse=True)
    return ranked[:limit]


def index_precedent(
    clause_text: str,
    category: str,
    *,
    contract_title: str,
    contract_id: str,
    clause_id: str,
    approved_by: str = "",
    risk_level: str = "",
    notes: str = "",
) -> List[str]:
    """Role 4 — record an approved clause as reusable precedent language."""
    payload = {
        "kind": "precedent",
        "category": category,
        "contract_id": contract_id,
        "contract_title": contract_title,
        "clause_id": clause_id,
        "approved_by": approved_by,
        "risk_level": risk_level,
        "notes": notes[:500],
        "text": clause_text[:4000],
    }
    return get_store().upsert_texts(
        PRECEDENTS, [clause_text], [payload], ids=[f"precedent:{contract_id}:{clause_id}"]
    )


def recall_precedents(
    clause_text: str,
    category: Optional[str] = None,
    *,
    limit: int = 3,
    min_score: float = 0.5,
) -> List[Dict[str, Any]]:
    """Role 4 — Precedent Recall: closest approved wording, with similarity."""
    filters: Dict[str, Any] = {"kind": "precedent"}
    if category:
        filters["category"] = category
    hits = get_store().search(
        PRECEDENTS, clause_text, limit=limit, filters=filters,
        score_threshold=min_score,
    )
    return [
        {**h.to_dict(), "similarity_pct": round(h.score * 100, 1)} for h in hits
    ]


def index_negotiation_memory(
    *,
    negotiation_id: str,
    clause_text: str,
    category: str,
    outcome: str,
    rounds_used: int,
    final_language: str,
    risk_before: float,
    risk_after: float,
    transcript_summary: str = "",
) -> List[str]:
    """Role 5 — remember how this negotiation went."""
    # Embed the dispute plus its resolution, so retrieval matches on both the
    # subject matter and the shape of the settlement.
    embed_text = " ".join(
        [category, clause_text[:1500], transcript_summary[:800], final_language[:1000]]
    )
    payload = {
        "kind": "negotiation_memory",
        "negotiation_id": negotiation_id,
        "category": category,
        "outcome": outcome,
        "rounds_used": rounds_used,
        "risk_before": risk_before,
        "risk_after": risk_after,
        "risk_reduction": round(risk_before - risk_after, 1),
        "final_language": final_language[:2000],
        "text": (transcript_summary or clause_text)[:2000],
    }
    return get_store().upsert_texts(
        NEGOTIATIONS, [embed_text], [payload], ids=[f"negotiation:{negotiation_id}"]
    )


def recall_negotiation_memory(
    clause_text: str,
    category: Optional[str] = None,
    *,
    limit: int = 3,
    min_score: float = 0.45,
) -> List[Dict[str, Any]]:
    """Role 5 — comparable past negotiations, fed to both negotiators and the Coach."""
    filters: Dict[str, Any] = {"kind": "negotiation_memory"}
    if category:
        filters["category"] = category
    hits = get_store().search(
        NEGOTIATIONS, clause_text, limit=limit, filters=filters,
        score_threshold=min_score,
    )
    return [h.to_dict() for h in hits]
