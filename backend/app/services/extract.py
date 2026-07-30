"""Document text extraction for PDF, DOCX and plain text."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB


class ExtractionError(Exception):
    """Raised when a document cannot be read at all."""


@dataclass
class ExtractedDocument:
    text: str
    page_count: int = 0
    char_count: int = 0
    method: str = ""
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_count": self.page_count,
            "char_count": self.char_count,
            "method": self.method,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }


def extract_document(data: bytes, filename: str) -> ExtractedDocument:
    """Dispatch on file extension, then normalise whitespace."""
    if not data:
        raise ExtractionError("Uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ExtractionError(
            f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit."
        )

    lower = (filename or "").lower()
    if lower.endswith(".pdf"):
        doc = _extract_pdf(data)
    elif lower.endswith(".docx"):
        doc = _extract_docx(data)
    elif lower.endswith((".txt", ".md")):
        doc = _extract_text(data)
    elif lower.endswith(".doc"):
        raise ExtractionError(
            "Legacy .doc is not supported. Please save as .docx or PDF and retry."
        )
    else:
        # Try UTF-8 before rejecting; many contracts arrive with no extension.
        try:
            doc = _extract_text(data)
            doc.warnings.append(
                f"Unrecognised extension for '{filename}'; parsed as plain text."
            )
        except ExtractionError:
            raise ExtractionError(
                f"Unsupported file type. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            )

    doc.text = normalize_whitespace(doc.text)
    doc.char_count = len(doc.text)

    if doc.char_count < 200:
        doc.warnings.append(
            "Very little text extracted. If this is a scanned document, it needs "
            "OCR before review — Dharma AI does not perform OCR."
        )
    return doc


def _extract_pdf(data: bytes) -> ExtractedDocument:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise ExtractionError("pypdf is not installed; cannot read PDF.") from exc

    warnings: List[str] = []
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:
        raise ExtractionError(f"Could not open PDF: {exc}") from exc

    if getattr(reader, "is_encrypted", False):
        # Many contract PDFs are "encrypted" with an empty owner password.
        try:
            reader.decrypt("")
            warnings.append("PDF was encrypted with an empty password; decrypted.")
        except Exception as exc:
            raise ExtractionError(
                "PDF is password-protected. Remove the password and re-upload."
            ) from exc

    pages: List[str] = []
    for i, page in enumerate(reader.pages):
        try:
            pages.append(page.extract_text() or "")
        except Exception as exc:
            warnings.append(f"Page {i + 1} could not be extracted ({exc}).")
            pages.append("")

    info: Dict[str, Any] = {}
    try:
        raw_meta = reader.metadata or {}
        for key in ("/Title", "/Author", "/Subject", "/CreationDate"):
            if raw_meta.get(key):
                info[key.lstrip("/").lower()] = str(raw_meta.get(key))[:200]
    except Exception:
        pass

    return ExtractedDocument(
        text="\n\n".join(pages),
        page_count=len(reader.pages),
        method="pypdf",
        warnings=warnings,
        metadata=info,
    )


def _extract_docx(data: bytes) -> ExtractedDocument:
    try:
        import docx
    except ImportError as exc:  # pragma: no cover
        raise ExtractionError("python-docx is not installed; cannot read DOCX.") from exc

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise ExtractionError(f"Could not open DOCX: {exc}") from exc

    blocks: List[str] = []
    for para in document.paragraphs:
        text = (para.text or "").strip()
        if not text:
            continue
        style = (para.style.name if para.style is not None else "") or ""
        # Preserve heading structure — clause splitting depends on it.
        if style.lower().startswith("heading"):
            blocks.append(f"\n\n{text}\n")
        else:
            blocks.append(text)

    # Contract tables often carry fee schedules and SLA terms; keep them.
    for table in document.tables:
        rows: List[str] = []
        for row in table.rows:
            cells = [(c.text or "").strip() for c in row.cells]
            if any(cells):
                rows.append(" | ".join(cells))
        if rows:
            blocks.append("\n" + "\n".join(rows))

    props: Dict[str, Any] = {}
    try:
        core = document.core_properties
        for attr in ("title", "author", "subject"):
            value = getattr(core, attr, None)
            if value:
                props[attr] = str(value)[:200]
    except Exception:
        pass

    return ExtractedDocument(
        text="\n\n".join(blocks),
        page_count=0,
        method="python-docx",
        metadata=props,
    )


def _extract_text(data: bytes) -> ExtractedDocument:
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return ExtractedDocument(
                text=data.decode(encoding), method=f"text/{encoding}"
            )
        except (UnicodeDecodeError, LookupError):
            continue
    raise ExtractionError("Could not decode file as text.")


_WS_RE = re.compile(r"[ \t ]+")
_NEWLINES_RE = re.compile(r"\n{3,}")
# Hyphenated line-wrap: "indemnifi-\ncation" -> "indemnification"
_HYPHEN_WRAP_RE = re.compile(r"(\w)-\n(\w)")


def normalize_whitespace(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _HYPHEN_WRAP_RE.sub(r"\1\2", text)
    text = _WS_RE.sub(" ", text)
    text = _NEWLINES_RE.sub("\n\n", text)
    return "\n".join(line.strip() for line in text.split("\n")).strip()
