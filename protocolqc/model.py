"""Core data types.

Design rule that everything else depends on: a Span is an *address* into a
document (page, line, column range) plus the exact characters found there.
Quotes shown to a reviewer are always rendered from Spans, never stored as
free text. That makes it impossible for this tool to display a quote that
is not literally in the source document.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterator, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class Span:
    """An exact character range on one line of one page."""

    doc: str  # document key: "protocol" | "report"
    page: int  # 1-based
    line: int  # 1-based, within the page
    start: int  # 0-based column offset within the line
    end: int  # exclusive
    text: str  # the exact characters at that address

    def locator(self) -> str:
        return f"p.{self.page} line {self.line}"


@dataclass
class Citation:
    """One or more spans that together make a quotable piece of evidence.

    `quote` is derived from the spans on demand -- it is deliberately not a
    stored string, so it cannot drift away from the document.
    """

    doc: str
    spans: List[Span]
    note: str = ""  # e.g. "Section 4, Reporting"

    @property
    def quote(self) -> str:
        """Spans rendered for display. Pieces from different lines are joined
        with a line break rather than a space, because gluing them together
        would present text that reads as continuous prose when it is not."""
        out: List[str] = []
        last_line: Optional[int] = None
        for s in self.spans:
            if not s.text.strip():
                continue
            piece = " ".join(s.text.split())
            if last_line is not None and s.line == last_line:
                out[-1] = out[-1] + " " + piece
            else:
                out.append(piece)
            last_line = s.line
        return "\n".join(out)

    @property
    def locator(self) -> str:
        if not self.spans:
            return ""
        page = self.spans[0].page
        lines = sorted({s.line for s in self.spans})
        if len(lines) == 1:
            return f"p.{page} line {lines[0]}"
        return f"p.{page} lines {lines[0]}-{lines[-1]}"


@dataclass
class Document:
    """A source document as text, addressable by page/line/column."""

    key: str
    name: str
    pages: List[List[str]]
    path: Optional[str] = None
    file_sha256: Optional[str] = None
    text_sha256: str = ""
    # A second, independent extraction of the same PDF (position-free). Used
    # only to license display-quote repair -- see quotes.py. Never used as
    # evidence, never addressed by a Span.
    flat_pages: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.text_sha256:
            self.text_sha256 = hashlib.sha256(
                self.full_text().encode("utf-8")
            ).hexdigest()

    # ---- addressing -------------------------------------------------
    def raw_line(self, page: int, line: int) -> str:
        return self.pages[page - 1][line - 1]

    def slice(self, page: int, line: int, start: int, end: int) -> str:
        """Characters at an address. Pads with spaces so an over-long end
        offset degrades to whitespace instead of silently truncating."""
        raw = self.raw_line(page, line)
        if end > len(raw):
            raw = raw.ljust(end)
        return raw[start:end]

    def span(self, page: int, line: int, start: int, end: int) -> Span:
        return Span(self.key, page, line, start, end, self.slice(page, line, start, end))

    def trimmed_span(self, page: int, line: int, start: int = 0,
                     end: Optional[int] = None) -> Optional[Span]:
        """Span over [start:end) with surrounding whitespace removed. Returns
        None when the range holds no printable characters."""
        raw = self.raw_line(page, line)
        end = len(raw) if end is None else min(end, len(raw))
        start = max(0, start)
        seg = raw[start:end]
        if not seg.strip():
            return None
        lead = len(seg) - len(seg.lstrip())
        trail = len(seg) - len(seg.rstrip())
        return self.span(page, line, start + lead, end - trail)

    def line_citation(self, page: int, lines: Sequence[int], note: str = "") -> Citation:
        spans = [s for ln in lines if (s := self.trimmed_span(page, ln)) is not None]
        return Citation(self.key, spans, note)

    # ---- searching --------------------------------------------------
    def iter_lines(self) -> Iterator[Tuple[int, int, str]]:
        for p, page in enumerate(self.pages, start=1):
            for ln, text in enumerate(page, start=1):
                yield p, ln, text

    def search(self, pattern: str, flags: int = re.I) -> List[Tuple[int, int, re.Match]]:
        rx = re.compile(pattern, flags)
        hits = []
        for p, ln, text in self.iter_lines():
            m = rx.search(text)
            if m:
                hits.append((p, ln, m))
        return hits

    def contains(self, pattern: str, flags: int = re.I) -> bool:
        return bool(re.search(pattern, self.full_text(), flags))

    def full_text(self) -> str:
        return "\n".join("\n".join(page) for page in self.pages)

    # ---- construction ----------------------------------------------
    @classmethod
    def from_text(cls, key: str, name: str, text: str, **kw) -> "Document":
        """Single entry point for building a Document, used by the PDF loader
        and by the mutation tests alike -- so tests exercise the same code
        path as production."""
        return cls(key=key, name=name, pages=[text.split("\n")], **kw)


@dataclass
class Finding:
    """An observation for a human reviewer. Deliberately has no pass/fail
    field: this tool describes what the documents say and how they differ,
    and stops there."""

    id: str
    rule_id: str
    rule_title: str
    category: str
    priority: str  # review priority (high|medium|low) -- NOT a verdict
    scope: str  # "T1", "T5", or "document"
    statement: str  # neutral description of what was observed
    basis: str  # the protocol requirement / reason this is checkable
    reviewer_action: str  # what the human is being asked to do
    citations: List[Citation] = field(default_factory=list)
    uncertainty: str = ""  # stated openly when the documents are ambiguous
    # "rule" for a deterministic check, "ai-suggested" for a model's advisory
    # observation. Suggestions travel in their own list and are never merged
    # into the findings, but the provenance rides along with each one anyway.
    source: str = "rule"



@dataclass
class RuleOutcome:
    """Recorded for every rule, whether or not it produced findings, so the
    output can distinguish 'checked, nothing found' from 'never looked'."""

    rule_id: str
    title: str
    category: str
    question: str
    fired: int
    status: str  # "findings" | "no-finding" | "not-applicable"
    detail: str = ""


# ---- text normalisation -------------------------------------------------

_SYMBOLS = {
    "≥": ">=",  # ≥
    "≤": "<=",  # ≤
    "–": "-",  # en dash
    "—": "-",  # em dash
    "−": "-",  # minus sign
    "µ": "u",  # µ
    "μ": "u",  # μ
}


def normalise(text: str) -> str:
    """Whitespace/symbol-insensitive form used only for *comparing* strings.
    Never used for anything shown to a reviewer."""
    text = unicodedata.normalize("NFKC", text)
    for src, dst in _SYMBOLS.items():
        text = text.replace(src, dst)
    text = re.sub(r"\s+", " ", text)
    # ">= 5.0" and ">=5.0" must compare equal.
    text = re.sub(r"(?<=[<>=])\s+(?=[\d.])", "", text)
    return text.strip().lower()


def squash(text: str) -> str:
    """Collapse whitespace for display without altering characters."""
    return " ".join(text.split())
