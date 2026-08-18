"""Finding model-supplied text in the real document.

This is the whole safety story for the AI path. A model returns a quote and a
line number; it never returns a character offset. This module searches the
document for that text and builds the Span from what it actually finds. A
quote that is not in the document cannot produce a Span, so it cannot reach a
reviewer -- and verify.py re-checks every surviving Span afterwards anyway.

Matching is whitespace-flexible in one direction only: runs of whitespace in
the model's quote may match runs of whitespace in the document. Every other
character must match exactly, and the Span always carries the document's
characters, never the model's.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from ..model import Document, Span


@dataclass
class LocateStats:
    located: int = 0
    line_hint_wrong: int = 0
    not_found: int = 0
    discarded: List[str] = field(default_factory=list)

    def note_discarded(self, what: str, quote: str) -> None:
        self.not_found += 1
        self.discarded.append(f"{what}: {quote[:80]!r} does not occur in the document")


def _pattern(quote: str) -> Optional[re.Pattern]:
    quote = quote.strip()
    if not quote:
        return None
    parts = [re.escape(p) for p in quote.split()]
    return re.compile(r"\s+".join(parts))


def locate(doc: Document, quote: str, line_hint: Optional[int], page: int = 1,
           stats: Optional[LocateStats] = None, what: str = "value") -> Optional[Span]:
    """Span for `quote` in `doc`, or None if the text is not there.

    The line hint is only a hint. Models miscount lines, so a failed hint falls
    back to a page-wide search -- the Span still records where the text really
    is, which is what makes the citation true.
    """
    rx = _pattern(quote)
    if rx is None:
        return None
    lines = doc.pages[page - 1]

    if line_hint and 1 <= line_hint <= len(lines):
        m = rx.search(lines[line_hint - 1])
        if m:
            if stats:
                stats.located += 1
            return doc.span(page, line_hint, m.start(), m.end())

    for idx, raw in enumerate(lines, start=1):
        m = rx.search(raw)
        if m:
            if stats:
                stats.located += 1
                if line_hint:
                    stats.line_hint_wrong += 1
            return doc.span(page, idx, m.start(), m.end())

    if stats:
        stats.note_discarded(what, quote)
    return None


# A hyphen between two alphanumerics is where a PDF breaks a word across lines
# ("Per ISO 10993-" + "5"). table.py already rejoins these when it builds a cell;
# this is the same rule on the search side, so the two do not disagree about
# whether a piece of text is in the document.
_HYPHEN_WRAP = re.compile(r"(?<=[0-9A-Za-z])-(?=[0-9A-Za-z])")

# How far the continuation may sit from the head's left edge. A wrapped cell
# resumes in its own column, so this is nearly zero in practice; a couple of
# characters absorbs the odd extraction wobble without letting an unrelated
# token on the next line pass as a continuation.
COLUMN_SLACK = 2


def _hyphen_wrapped(doc: Document, quote: str, page: int) -> List[Span]:
    """Spans for a quote whose word was split across a line break by a hyphen.

    Two conditions, both required. The hyphen must end the text on its line --
    otherwise the head is a coincidental prefix of something longer. And the
    continuation must resume in the same column, which is what a wrapped table
    cell does and what an unrelated token on the next line does not. Without
    the column test, "Per ISO 10993-5" would happily bind to any stray "5"
    below it and produce a citation pointing at the wrong place.
    """
    lines = doc.pages[page - 1]
    for m in _HYPHEN_WRAP.finditer(quote):
        head, tail = quote[: m.end()], quote[m.end():]
        rx_head, rx_tail = _pattern(head), _pattern(tail)
        if rx_head is None or rx_tail is None:
            continue
        for idx, raw in enumerate(lines, start=1):
            if idx >= len(lines):
                break
            mh = rx_head.search(raw)
            # The hyphen has to be the last thing in its cell on this line.
            if not mh or raw[mh.end(): mh.end() + 1].strip():
                continue
            for mt in rx_tail.finditer(lines[idx]):
                if abs(mt.start() - mh.start()) <= COLUMN_SLACK:
                    return [doc.span(page, idx, mh.start(), mh.end()),
                            doc.span(page, idx + 1, mt.start(), mt.end())]
    return []


def locate_all(doc: Document, quote: str, line_hint: Optional[int], page: int = 1,
               stats: Optional[LocateStats] = None, what: str = "value") -> List[Span]:
    """As locate(), but a quote that wraps across lines yields one Span per
    line. Used for cells and sentences that the PDF broke mid-phrase."""
    # First attempt without stats: a quote that only matches once split across
    # lines is not a miss, and must not be recorded as one.
    single = locate(doc, quote, line_hint, page, None, what)
    if single is not None:
        if stats:
            stats.located += 1
        return [single]

    hyphenated = _hyphen_wrapped(doc, quote, page)
    if hyphenated:
        if stats:
            stats.located += 1
        return hyphenated

    words = quote.split()
    if len(words) < 4:
        if stats:
            stats.note_discarded(what, quote)
        return []

    # Try progressively shorter prefixes and match the remainder on the next
    # line. Anything still unmatched is dropped rather than approximated.
    lines = doc.pages[page - 1]
    for split in range(len(words) - 1, 1, -1):
        head, tail = " ".join(words[:split]), " ".join(words[split:])
        rx_head, rx_tail = _pattern(head), _pattern(tail)
        if not rx_head or not rx_tail:
            continue
        for idx, raw in enumerate(lines, start=1):
            mh = rx_head.search(raw)
            if not mh or idx >= len(lines):
                continue
            mt = rx_tail.search(lines[idx])
            if mt:
                if stats:
                    stats.located += 1
                return [
                    doc.span(page, idx, mh.start(), mh.end()),
                    doc.span(page, idx + 1, mt.start(), mt.end()),
                ]
    if stats:
        stats.note_discarded(what, quote)
    return []


def numbered(doc: Document, page: int = 1) -> str:
    """The document as the model sees it: every line prefixed with its number."""
    return "\n".join(
        f"{i:4d}| {raw}" for i, raw in enumerate(doc.pages[page - 1], start=1)
    )
