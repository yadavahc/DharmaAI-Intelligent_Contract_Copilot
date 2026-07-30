# Qdrant Usage in Dharma AI

Qdrant is not used as a place to park embeddings. It serves **five distinct
retrieval roles across four collections**, each queried with different filters and
thresholds, and each feeding a specific agent decision.

**Verify it live:**

```bash
curl localhost:8000/api/vector/health         # collections, point counts, purposes
curl localhost:8000/api/search/scopes         # the four searchable scopes
```

Or open **Semantic Search** in the app, which lets you query all four directly.

---

## Collections

| Collection | Points hold | Retrieved for |
| --- | --- | --- |
| `dharma_clauses` | Every clause of every ingested contract | Roles 1 & 2 |
| `dharma_playbook` | Every active admin playbook rule | Role 3 |
| `dharma_precedents` | Approved clause wording | Role 4 |
| `dharma_negotiations` | Completed negotiations + outcomes | Role 5 |

All four use cosine distance at the configured embedding dimension (1536 for
`text-embedding-3-small`).

---

## Role 1 — Semantic clause search

**`search_clauses(query, category?, contract_id?, risk_level?)`**

Powers the Search page. The filters are the point: this is a vector query **plus**
a payload constraint evaluated inside Qdrant, not a post-filter in Python. That
makes queries like *"every uncapped-liability clause rated High across all
contracts"* a single request:

```python
store.search(
    CLAUSES, query,
    limit=10,
    filters={"kind": "clause", "category": "Liability", "risk_level": "High"},
)
```

A keyword search cannot answer *"uncapped exposure"* over text that says
"Supplier shall have no limitation on liability" — vector search can.

## Role 2 — Similar-clause matching

**`find_similar_clauses(clause_text, category, exclude_contract_id)`**

Feeds the **Risk Assessment Agent**, so a score is grounded in how comparable
language was treated before rather than in model intuition alone.

Two details that matter:

* **The source contract is excluded.** A clause is trivially similar to itself, and
  self-matches would make the retrieval *look* impressive while adding nothing.
* **Category-scoped.** A Liability clause is compared against Liability clauses.

## Role 3 — Playbook RAG

**`retrieve_playbook_rules(clause_text, category)`**

Rules are embedded on their *meaning* — title + category + guidance + keywords +
preferred language — not their JSON, so a clause matches the rules that are
actually about it.

Retrieval runs **twice and merges**: once scoped to the clause's category, once for
global (`*`) rules, de-duplicated keeping the higher score. Category-scoped
retrieval alone would miss company-wide rules; global-only would let them drown out
the specific ones.

Why retrieve at all rather than send the whole playbook? With 14 rules you could
inline them; with 300 you cannot, and precision degrades long before the context
limit does. Retrieval keeps the prompt to the handful of rules that matter.

**Important:** retrieval decides what the *agent reads*. It never decides whether a
rule *fires*. Every deterministically-checkable rule (monetary and duration
thresholds) is also evaluated in Python against the full rule set — a $250,000
liability cap must trip the $100K threshold whether or not the rule text was
semantically similar to the clause. See `ingest.py`, where the retrieved set is
unioned with the complete set before scoring.

## Role 4 — Precedent Recall *(signature feature 4)*

**`recall_precedents(clause_text, category)`** → `dharma_precedents`

Surfaces the closest **previously approved** wording as recommended language, with
a similarity score.

The library is not static — it is a feedback loop. When a Reviewer approves or
edits a redline, that human-accepted wording is written back as new precedent
(`routers/review.py`):

```
Reviewer approves redline ──► index_precedent(final_text, category, approved_by=…)
                                        │
                                        ▼
                        available to the next contract's Redline Agent
```

So the system's suggestions improve as your team uses it, grounded in language your
own counsel has already signed off. Verified end to end: the Playwright run
approves one redline and the precedent count goes 7 → 8.

## Role 5 — Negotiation memory

**`recall_negotiation_memory(clause_text, category)`** → `dharma_negotiations`

Consumed by **both negotiators and the Strategy Coach**, so agents open from
precedent instead of from scratch, and the Coach's acceptance probability is
anchored to observed outcomes rather than guesswork.

The embedded text combines the dispute *and* its resolution — category + clause +
transcript summary + final language — so retrieval matches on both the subject
matter and the shape of the settlement. The payload carries `outcome`,
`rounds_used`, `risk_before`, `risk_after` and `risk_reduction`.

---

## Where each role is consumed

```
Ingest ─────────► index_clauses()                        [writes role 1 & 2]
                        │
Per clause:             │
  Classification        │
        ▼               │
  Playbook Validation ◄─┼─ retrieve_playbook_rules()     [role 3]
        ▼               │
  Risk Assessment    ◄──┴─ find_similar_clauses()        [role 2]
        ▼
  Redline            ◄──── recall_precedents()           [role 4]
        ▼
Negotiation:
  Organization Agent ◄─┬── recall_negotiation_memory()   [role 5]
  Counterparty Agent ◄─┤
  Strategy Coach     ◄─┘
        ▼
  index_negotiation_memory()                             [writes role 5]

Human approval ────────► index_precedent()               [writes role 4]
```

---

## Embeddings

Live mode uses OpenAI `text-embedding-3-small` (1536-d), batched 96 at a time, with
results re-sorted by index because ordering is not contractually guaranteed. A
dimension mismatch raises rather than silently corrupting a collection.

**Demo mode** (no API key) uses a local hashed-feature embedding so that all five
retrieval roles still return meaningful results offline. It is a real vector-space
model, not noise: word and character n-grams hashed into the same 1536 dimensions
with sublinear term weighting and L2 normalisation, so cosine similarity tracks
lexical overlap.

Two honest caveats:

1. **It does not know synonyms a transformer knows.** To compensate, a curated
   legal-synonym map collapses known equivalents onto shared canonical tokens
   (`"unlimited liability"`, `"no cap on liability"`, `"uncapped liability"` →
   `zz_uncapped_liability`). Crude, but contract language is formulaic enough that
   it ranks sensibly.
2. **Its similarity scores sit on a different scale.** Transformer embeddings put
   related contract text around 0.6–0.9; hashed features rarely exceed 0.35 even
   for close paraphrases. Thresholds are expressed on the transformer scale and
   rescaled for whichever backend produced the vectors (`scale_threshold()`) —
   without that, every similarity search returns empty in demo mode.

So a Precedent Recall card may read "25% match" in demo mode where a live key gives
"87%". That is the local embedder being honest about itself, not a bug — and
`/api/health` always reports which embedding method is live.

### Guarding against mixed vector spaces

Vectors from two different embedding models are **not comparable**. Cosine
similarity between an OpenAI vector and a locally-hashed one is noise, not a weak
match — and noise that still returns confident-looking percentages.

This is a live hazard, not a theoretical one. Run in demo mode with no key, seed
the precedent library, then add an API key: every stored vector is now in the wrong
space. Observed before the fix — a query for *"aggregate liability capped at twelve
months of fees"* scored its exact-match precedent at **5%**.

So every point carries an `_embedding` signature (`openai/text-embedding-3-small:1536`
or `local-hashed:1536`). At startup `check_embedding_consistency()` samples each
collection and compares:

* `dharma_playbook` and `dharma_precedents` are **rebuilt automatically** — they are
  derived data and cheap to regenerate.
* `dharma_clauses` and `dharma_negotiations` cannot be regenerated without re-running
  the agents, so they are **reported loudly** with instructions (re-run the review,
  or `POST /api/demo/reset`) rather than left to return meaningless scores.

After the repair the same query scores its precedent at **64%**, and a playbook
query for *"supplier can change the contract whenever it likes"* correctly retrieves
`PB-GLOBAL-001: Unilateral amendment rights are prohibited` — with no shared
keywords, which is the whole point of doing this with vectors.

---

## Degradation

If Qdrant is unreachable, an in-process brute-force cosine index takes over with
identical semantics — same filters, same thresholds, same call signatures. The demo
keeps working on a laptop with no Docker, and the code path a reviewer reads is the
real one. `/api/health` reports `backend: "in-memory"` and the Settings page says
so, with the caveat that vectors are not persisted.

Point ids are UUID5-derived from a stable key (`{collection}:{contract_id}:{clause_id}`),
so re-ingesting or re-reviewing a clause updates in place instead of duplicating.

---

## Configuration

```bash
QDRANT_URL=http://localhost:6333      # or https://<cluster>.cloud.qdrant.io:6333
QDRANT_API_KEY=                       # required for Qdrant Cloud
```

Both local (Docker Compose) and Qdrant Cloud are supported with no code change —
collections are created on first connect if absent. Verified against both.
