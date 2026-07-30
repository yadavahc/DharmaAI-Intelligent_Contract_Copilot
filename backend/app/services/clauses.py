"""
Splitting a contract into clauses.

Everything downstream — classification, risk, redlines, embeddings — operates on
whatever this module decides a "clause" is, so getting the units right matters
more than any single agent prompt.

Strategy, in order of preference:

  1. **Numbered structure.** Real contracts are numbered (`1.`, `2.3`, `12.1.4`,
     `Article IV`, `Section 7`). When numbering is present it is by far the most
     reliable signal, so we anchor on it and keep the label and heading.
  2. **ALL-CAPS / title-case headings.** Common in NDAs and short-form
     agreements that skip numbering.
  3. **Paragraph fallback.** Blank-line separated blocks, greedily merged toward
     a target size.

Oversized clauses are then split at sentence boundaries, and undersized
fragments (stray page numbers, signature lines) are merged into their neighbour,
so no clause is too big to reason about or too small to be meaningful.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Tuning: characters, not tokens — cheap to compute and good enough.
TARGET_MAX_CHARS = 2400
HARD_MAX_CHARS = 4000
MIN_CLAUSE_CHARS = 120


@dataclass
class Clause:
    index: int
    label: str  # "12.1", "Article IV", or ""
    heading: str  # "Limitation of Liability"
    text: str
    char_start: int = 0
    char_end: int = 0
    split_method: str = ""
    notes: List[str] = field(default_factory=list)

    @property
    def display_title(self) -> str:
        if self.label and self.heading:
            return f"{self.label} {self.heading}"
        return self.heading or self.label or f"Clause {self.index + 1}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "label": self.label,
            "heading": self.heading,
            "display_title": self.display_title,
            "text": self.text,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "char_count": len(self.text),
            "split_method": self.split_method,
            "notes": self.notes,
        }


# ── numbering patterns ──────────────────────────────────────────────────────
# "12.1 Limitation of Liability." / "3. Payment" / "1.2.3 Sub-clause"
_NUMBERED_RE = re.compile(
    r"^(?P<label>\d{1,2}(?:\.\d{1,2}){0,3})\.?\s+(?P<rest>\S.*)$"
)
# "Section 7. Confidentiality" / "ARTICLE IV — Term"
_SECTION_RE = re.compile(
    r"^(?P<label>(?:section|article|clause|schedule|exhibit|appendix|annex)\s+"
    r"(?:\d{1,3}|[ivxlcIVXLC]{1,7}|[A-Z]))\b[.:—–-]?\s*(?P<rest>.*)$",
    re.IGNORECASE,
)
# "(a) Sub-item" / "(iv) Another"
_LETTERED_RE = re.compile(r"^\((?P<label>[a-z]{1,2}|[ivxlc]{1,5})\)\s+(?P<rest>\S.*)$")

_ALLCAPS_RE = re.compile(r"^(?P<heading>[A-Z][A-Z0-9 ,&'/()\-\.]{4,70})$")

# Heading text at the start of a clause body: "Limitation of Liability. The ..."
_INLINE_HEADING_RE = re.compile(
    r"^(?P<heading>[A-Z][A-Za-z /&'\-]{3,60}?)\s*[.:—–-]\s+(?=[A-Z(])"
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.;])\s+(?=[A-Z(\"'“])")

# Lines that are structural noise rather than contract content.
_NOISE_RE = re.compile(
    r"^(?:page\s+\d+(?:\s+of\s+\d+)?|\d+|[-_=*\s]{3,}|"
    r"(?:signature|signed|by|name|title|date)\s*:?\s*_*)$",
    re.IGNORECASE,
)


def split_into_clauses(text: str) -> List[Clause]:
    """Split contract text into clauses. Always returns at least one clause."""
    if not text or not text.strip():
        return []

    lines = text.split("\n")
    starts = _find_structural_starts(lines)

    if len(starts) >= 3:
        clauses = _split_by_starts(text, lines, starts)
        method = "structural"
    else:
        clauses = _split_by_paragraphs(text)
        method = "paragraph"

    for clause in clauses:
        if not clause.split_method:
            clause.split_method = method

    clauses = _enforce_size_limits(clauses)
    clauses = _merge_undersized(clauses)

    for i, clause in enumerate(clauses):
        clause.index = i
        if not clause.heading:
            clause.heading = _infer_heading(clause.text)

    return clauses


# ─────────────────────────────────────────────────────────────────────────────


def _find_structural_starts(lines: List[str]) -> List[Dict[str, Any]]:
    """Locate lines that begin a new clause, with their label and heading."""
    starts: List[Dict[str, Any]] = []
    for i, raw in enumerate(lines):
        line = raw.strip()
        if not line or _NOISE_RE.match(line):
            continue

        match = _SECTION_RE.match(line)
        if match:
            starts.append(
                {
                    "line": i,
                    "label": _tidy_label(match.group("label")),
                    "heading": _tidy_heading(match.group("rest")),
                    "kind": "section",
                }
            )
            continue

        match = _NUMBERED_RE.match(line)
        if match:
            rest = match.group("rest")
            # Guard against ordinary prose that happens to start with a number,
            # e.g. "30 days written notice ..." — a real clause label is followed
            # by a heading or a capitalised sentence.
            if _looks_like_clause_open(rest):
                starts.append(
                    {
                        "line": i,
                        "label": match.group("label"),
                        "heading": _tidy_heading(rest),
                        "kind": "numbered",
                    }
                )
            continue

        match = _ALLCAPS_RE.match(line)
        if match and len(line.split()) <= 9:
            starts.append(
                {
                    "line": i,
                    "label": "",
                    "heading": _tidy_heading(match.group("heading")),
                    "kind": "allcaps",
                }
            )
            continue

    # Sub-items like "(a)" only count as clause boundaries when there is no
    # higher-level numbering at all; otherwise they fragment clauses.
    if not starts:
        for i, raw in enumerate(lines):
            match = _LETTERED_RE.match(raw.strip())
            if match:
                starts.append(
                    {
                        "line": i,
                        "label": f"({match.group('label')})",
                        "heading": _tidy_heading(match.group("rest")),
                        "kind": "lettered",
                    }
                )
    return starts


def _looks_like_clause_open(rest: str) -> bool:
    if not rest:
        return False
    first = rest.split()[0] if rest.split() else ""
    # "12.1 Limitation ..." — capitalised opener is the signal.
    if first[:1].isupper():
        return True
    return bool(_INLINE_HEADING_RE.match(rest))


def _split_by_starts(
    text: str, lines: List[str], starts: List[Dict[str, Any]]
) -> List[Clause]:
    # Offset of each line within the original text, for char_start/char_end.
    offsets: List[int] = []
    cursor = 0
    for line in lines:
        offsets.append(cursor)
        cursor += len(line) + 1

    clauses: List[Clause] = []

    # Anything before the first structural start is a preamble worth keeping.
    first_line = starts[0]["line"]
    if first_line > 0:
        preamble = "\n".join(lines[:first_line]).strip()
        if len(preamble) >= MIN_CLAUSE_CHARS:
            clauses.append(
                Clause(
                    index=0,
                    label="",
                    heading="Preamble",
                    text=preamble,
                    char_start=0,
                    char_end=offsets[first_line],
                    split_method="structural",
                )
            )

    for n, start in enumerate(starts):
        begin = start["line"]
        end = starts[n + 1]["line"] if n + 1 < len(starts) else len(lines)
        body = "\n".join(lines[begin:end]).strip()
        if not body:
            continue
        clauses.append(
            Clause(
                index=len(clauses),
                label=start["label"],
                heading=start["heading"],
                text=body,
                char_start=offsets[begin],
                char_end=offsets[end - 1] + len(lines[end - 1]) if end > begin else offsets[begin],
                split_method="structural",
            )
        )
    return clauses


def _split_by_paragraphs(text: str) -> List[Clause]:
    """Greedily merge blank-line separated blocks toward the target size."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    blocks = [b for b in blocks if not _NOISE_RE.match(b)]

    clauses: List[Clause] = []
    buffer: List[str] = []
    cursor = 0
    buffer_start = 0

    def flush() -> None:
        nonlocal buffer, buffer_start
        if not buffer:
            return
        body = "\n\n".join(buffer)
        clauses.append(
            Clause(
                index=len(clauses),
                label="",
                heading="",
                text=body,
                char_start=buffer_start,
                char_end=buffer_start + len(body),
                split_method="paragraph",
            )
        )
        buffer = []

    for block in blocks:
        if not buffer:
            buffer_start = cursor
        current = sum(len(b) for b in buffer)
        if buffer and current + len(block) > TARGET_MAX_CHARS:
            flush()
            buffer_start = cursor
        buffer.append(block)
        cursor += len(block) + 2

    flush()
    return clauses


def _enforce_size_limits(clauses: List[Clause]) -> List[Clause]:
    """Split clauses over the hard cap at sentence boundaries."""
    out: List[Clause] = []
    for clause in clauses:
        if len(clause.text) <= HARD_MAX_CHARS:
            out.append(clause)
            continue

        sentences = _SENTENCE_SPLIT_RE.split(clause.text)
        chunk: List[str] = []
        part = 1
        for sentence in sentences:
            projected = sum(len(s) for s in chunk) + len(sentence)
            if chunk and projected > TARGET_MAX_CHARS:
                out.append(_sub_clause(clause, chunk, part))
                part += 1
                chunk = []
            chunk.append(sentence)
        if chunk:
            out.append(_sub_clause(clause, chunk, part))
    return out


def _sub_clause(parent: Clause, sentences: List[str], part: int) -> Clause:
    label = f"{parent.label} (part {part})" if parent.label else ""
    return Clause(
        index=0,
        label=label,
        heading=parent.heading,
        text=" ".join(sentences).strip(),
        char_start=parent.char_start,
        char_end=parent.char_end,
        split_method=f"{parent.split_method}+sentence",
        notes=[f"Split from oversized clause {parent.display_title!r} (part {part})."],
    )


def _merge_undersized(clauses: List[Clause]) -> List[Clause]:
    """Fold tiny fragments into a neighbour so every clause is substantive."""
    if len(clauses) <= 1:
        return clauses

    out: List[Clause] = []
    for clause in clauses:
        # A clause carrying both an explicit label and a heading ("1. Definitions")
        # is deliberate document structure. Merging it away because it is short
        # would silently destroy a real clause boundary, so length alone never
        # merges one — only genuinely unlabelled fragments get folded in.
        is_explicit = bool(clause.label and clause.heading)
        if (
            out
            and not is_explicit
            and len(clause.text) < MIN_CLAUSE_CHARS
            and len(out[-1].text) + len(clause.text) <= HARD_MAX_CHARS
        ):
            previous = out[-1]
            previous.text = f"{previous.text}\n{clause.text}".strip()
            previous.char_end = max(previous.char_end, clause.char_end)
            previous.notes.append("Merged a short trailing fragment.")
            continue
        out.append(clause)

    # A short leading clause merges forward instead — but, as above, only when it
    # is an unlabelled fragment (a stray title line) rather than a real numbered
    # clause. Without this guard, "1. Definitions." gets absorbed into clause 2.
    if (
        len(out) > 1
        and len(out[0].text) < MIN_CLAUSE_CHARS
        and not (out[0].label and out[0].heading)
    ):
        head, nxt = out[0], out[1]
        nxt.text = f"{head.text}\n{nxt.text}".strip()
        nxt.char_start = head.char_start
        nxt.notes.append("Merged a short leading fragment.")
        out = out[1:]

    return out


def _tidy_label(label: str) -> str:
    return " ".join(w.capitalize() if w.isalpha() else w.upper() for w in label.split())


def _tidy_heading(rest: str) -> str:
    """Pull a heading out of the text following a clause label."""
    rest = (rest or "").strip()
    if not rest:
        return ""

    match = _INLINE_HEADING_RE.match(rest)
    if match:
        return match.group("heading").strip()

    # A short remainder is itself the heading.
    if len(rest) <= 70 and not rest.endswith((".", ";")):
        return rest.strip(" .:—–-")

    # Otherwise take the leading title-case run.
    words = rest.split()
    title_words: List[str] = []
    for word in words[:8]:
        if word[:1].isupper() or word.lower() in ("of", "and", "or", "the", "to", "for"):
            title_words.append(word)
        else:
            break
    if len(title_words) >= 2:
        return " ".join(title_words).strip(" .:—–-")
    return ""


def _infer_heading(text: str) -> str:
    match = _INLINE_HEADING_RE.match(text.strip())
    if match:
        return match.group("heading").strip()
    first = text.strip().split("\n", 1)[0]
    return (first[:60] + "…") if len(first) > 60 else first
