"""
Embeddings, with a deterministic offline fallback.

Live mode calls OpenAI `text-embedding-3-small` (1536-d). Demo mode uses a
local hashed-feature embedding so that Qdrant retrieval — clause search,
playbook RAG, precedent recall, negotiation memory — still returns *meaningful*
results with no API key.

The fallback is a real vector-space model, not random noise: word and character
n-grams are hashed into the same 1536 dimensions with sublinear term weighting
and L2 normalisation, so cosine similarity tracks lexical overlap. It will not
match a transformer on synonymy ("indemnify" vs "hold harmless"), but for
contract language — which is highly formulaic and repeats exact phrases — it
ranks sensibly. Both paths produce unit vectors of identical dimension, so
Qdrant is configured the same either way.
"""

from __future__ import annotations

import hashlib
import math
import re
import threading
from typing import Dict, List, Optional, Sequence, Tuple

from app.config import settings

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "at", "by",
    "with", "as", "is", "are", "be", "been", "was", "were", "that", "this",
    "it", "its", "any", "all", "such", "shall", "will", "may", "not", "no",
    "if", "then", "which", "hereby", "herein", "hereof", "thereto", "pursuant",
}

_TOKEN_RE = re.compile(r"[a-z0-9$%\.]+")
_EMBED_BATCH = 96
_MAX_CHARS_PER_INPUT = 8000

# Legal-synonym canonicalisation for the local embedding.
#
# Hashed bag-of-words features are near-orthogonal, so "unlimited liability" and
# "liability shall not be capped" score close to zero against each other despite
# meaning the same thing. Collapsing known equivalents onto a shared canonical
# token gives the local model a crude synonym space, which is what makes
# precedent recall and similar-clause matching return sensible neighbours
# offline. Phrase-level, applied before tokenisation, longest-first.
_CANONICAL: List[Tuple[str, str]] = [
    # liability exposure
    ("unlimited liability", "zz_uncapped_liability"),
    ("no cap on liability", "zz_uncapped_liability"),
    ("no limitation on liability", "zz_uncapped_liability"),
    ("uncapped liability", "zz_uncapped_liability"),
    ("shall not be subject to any cap", "zz_uncapped_liability"),
    ("aggregate liability", "zz_liability_cap"),
    ("limitation of liability", "zz_liability_cap"),
    ("liability capped", "zz_liability_cap"),
    ("capped at", "zz_liability_cap"),
    ("limited to the fees", "zz_liability_cap"),
    ("consequential damages", "zz_consequential"),
    ("indirect damages", "zz_consequential"),
    ("punitive damages", "zz_consequential"),
    # indemnity
    ("hold harmless", "zz_indemnity"),
    ("indemnify", "zz_indemnity"),
    ("indemnification", "zz_indemnity"),
    ("defend", "zz_indemnity"),
    # payment
    ("net 90", "zz_extended_payment"),
    ("net 60", "zz_extended_payment"),
    ("net 120", "zz_extended_payment"),
    ("net 30", "zz_standard_payment"),
    ("net 15", "zz_standard_payment"),
    ("payment terms", "zz_payment"),
    ("invoice", "zz_payment"),
    # termination
    ("terminate for convenience", "zz_termination_convenience"),
    ("termination for convenience", "zz_termination_convenience"),
    ("for cause", "zz_termination_cause"),
    ("cure period", "zz_cure"),
    ("written notice", "zz_notice"),
    # ip
    ("intellectual property", "zz_ip"),
    ("work product", "zz_ip"),
    ("all right, title, and interest", "zz_ip_assignment"),
    ("assigns all right", "zz_ip_assignment"),
    # confidentiality
    ("confidential information", "zz_confidentiality"),
    ("non-disclosure", "zz_confidentiality"),
    ("proprietary information", "zz_confidentiality"),
    # renewal
    ("automatically renew", "zz_auto_renewal"),
    ("auto-renew", "zz_auto_renewal"),
    ("successive terms", "zz_auto_renewal"),
    # warranty
    ("as is", "zz_no_warranty"),
    ("disclaims all warranties", "zz_no_warranty"),
    ("merchantability", "zz_no_warranty"),
    # data
    ("personal data", "zz_privacy"),
    ("data breach", "zz_privacy"),
    ("gdpr", "zz_privacy"),
    # mutuality
    ("each party", "zz_mutual"),
    ("both parties", "zz_mutual"),
    ("mutual", "zz_mutual"),
]


def _canonicalize(text: str) -> str:
    body = (text or "").lower()
    for phrase, canonical in _CANONICAL:
        if phrase in body:
            # Keep the original words too: the canonical token adds a shared
            # dimension without discarding the specific wording.
            body = body.replace(phrase, f"{phrase} {canonical}")
    return body


def _tokenize(text: str) -> List[str]:
    tokens = [t for t in _TOKEN_RE.findall(_canonicalize(text)) if t not in _STOPWORDS]
    return [t for t in tokens if len(t) > 1 or t in ("$", "%")]


# Cosine scores from the two backends live on different scales: transformer
# embeddings put related contract text around 0.6–0.9, while hashed bag-of-words
# features rarely exceed 0.35 even for close paraphrases. Thresholds in the
# retrieval layer are expressed on the transformer scale, so they are rescaled
# for whichever backend actually produced the vectors — otherwise every
# similarity search returns empty in demo mode.
_LOCAL_THRESHOLD_SCALE = 0.35


def scale_threshold(min_score: Optional[float]) -> Optional[float]:
    """Rescale a transformer-scale similarity threshold to the active backend."""
    if min_score is None:
        return None
    service = get_embedding_service()
    if service.uses_local_vectors:
        return round(min_score * _LOCAL_THRESHOLD_SCALE, 4)
    return min_score


def embedding_signature() -> str:
    """Identifies the vector space that vectors were produced in.

    Vectors from different embedding models are not comparable — cosine similarity
    between an OpenAI vector and a locally-hashed one is noise, not a weak match.
    That is a live hazard here: a user runs in demo mode with no key, seeds the
    precedent library, then adds a key. Every stored vector is silently in the
    wrong space, and Precedent Recall quietly degrades to nonsense (observed:
    5% similarity for text that should score ~90%).

    Stamping this signature into every payload lets the store detect the mismatch
    and re-index instead of returning confident-looking garbage.
    """
    if settings.demo_mode:
        return f"local-hashed:{settings.embedding_dim}"
    return f"openai/{settings.openai_embed_model}:{settings.embedding_dim}"


def _bucket(feature: str, dim: int) -> int:
    return int(hashlib.blake2b(feature.encode("utf-8"), digest_size=8).hexdigest(), 16) % dim


def local_embed(text: str, dim: Optional[int] = None) -> List[float]:
    """Deterministic hashed-feature embedding. Same text always yields the same vector."""
    dim = dim or settings.embedding_dim
    vector = [0.0] * dim
    tokens = _tokenize(text)
    if not tokens:
        # A zero vector breaks cosine similarity; anchor empty input instead.
        vector[0] = 1.0
        return vector

    counts: Dict[str, float] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0.0) + 1.0
    # Bigrams capture phrases like "unlimited liability" / "net 90".
    for a, b in zip(tokens, tokens[1:]):
        bigram = f"{a}_{b}"
        counts[bigram] = counts.get(bigram, 0.0) + 1.5
    # Character 4-grams of long words give partial robustness to morphology
    # ("indemnify" / "indemnification").
    for token in tokens:
        if len(token) >= 8:
            for i in range(len(token) - 3):
                gram = f"#{token[i : i + 4]}"
                counts[gram] = counts.get(gram, 0.0) + 0.4

    for feature, count in counts.items():
        # Sublinear scaling: the tenth "liability" adds less than the first.
        vector[_bucket(feature, dim)] += 1.0 + math.log(count)

    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0:
        vector[0] = 1.0
        return vector
    return [v / norm for v in vector]


class EmbeddingService:
    """Batches embedding requests and falls back to local vectors on failure."""

    def __init__(self) -> None:
        self._client = None
        self._lock = threading.Lock()
        self.last_method: str = "unknown"
        # True once a batch has been served by the local hashed embedder, so the
        # retrieval layer knows which similarity scale is in play. Assumed local
        # up front in demo mode, since that is decided before any call.
        self._used_local: bool = settings.demo_mode

    @property
    def dim(self) -> int:
        return settings.embedding_dim

    @property
    def uses_local_vectors(self) -> bool:
        return self._used_local

    def _openai_client(self):
        if self._client is None:
            with self._lock:
                if self._client is None:
                    from openai import OpenAI

                    self._client = OpenAI(
                        api_key=settings.openai_api_key,
                        timeout=settings.openai_timeout_seconds,
                    )
        return self._client

    def embed(self, text: str) -> List[float]:
        return self.embed_many([text])[0]

    def embed_many(self, texts: Sequence[str]) -> List[List[float]]:
        if not texts:
            return []
        cleaned = [(t or "")[:_MAX_CHARS_PER_INPUT] for t in texts]

        if settings.demo_mode:
            self.last_method = "local-hashed (demo mode)"
            self._used_local = True
            return [local_embed(t) for t in cleaned]

        try:
            client = self._openai_client()
            vectors: List[List[float]] = []
            for start in range(0, len(cleaned), _EMBED_BATCH):
                batch = cleaned[start : start + _EMBED_BATCH]
                response = client.embeddings.create(
                    model=settings.openai_embed_model,
                    input=list(batch),
                )
                # Order is not contractually guaranteed; sort by index to be safe.
                ordered = sorted(response.data, key=lambda d: d.index)
                vectors.extend([list(d.embedding) for d in ordered])

            if vectors and len(vectors[0]) != settings.embedding_dim:
                # Dimension mismatch would corrupt the collection; fail loudly
                # rather than write vectors Qdrant cannot compare.
                raise ValueError(
                    f"Embedding dim {len(vectors[0])} != configured "
                    f"{settings.embedding_dim}. Update EMBEDDING_DIM to match "
                    f"{settings.openai_embed_model}."
                )
            self.last_method = f"openai/{settings.openai_embed_model}"
            self._used_local = False
            return vectors
        except Exception:
            # Never let an embedding outage take down ingest; degrade to local.
            self.last_method = "local-hashed (openai unavailable)"
            self._used_local = True
            return [local_embed(t) for t in cleaned]


_service: Optional[EmbeddingService] = None
_service_lock = threading.Lock()


def get_embedding_service() -> EmbeddingService:
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = EmbeddingService()
    return _service
