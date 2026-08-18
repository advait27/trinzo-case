"""Structured view of each document: header metadata, sections, test table.

This layer only reports what the documents *say*. It makes no comparison and
holds no opinion -- all judgement lives in rules.py, so the two can be
reviewed and changed independently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

from .model import Citation, Document, squash
from .normalize import parse_date
from .table import Row, Table, parse_table

HEADER_KV = re.compile(r"^\s*([A-Za-z][A-Za-z /]{2,30}):\s+(\S.*)$")
SECTION = re.compile(r"^\s{0,3}(\d+)\.\s+(\S.*)$")
BULLET = re.compile(r"^\s*[●•▪·o]\s+(\S.*)$")
DOC_ID = re.compile(r"\b([A-Z]{2,4}-\d{2,4}-[A-Z]{2,3}-\d{2,4})\b")
VERSION_REF = re.compile(r"version\s*([\d.]+)", re.I)


@dataclass
class Field:
    """A header field with the line it came from, so it can be cited."""

    key: str
    value: str
    page: int
    line: int

    def citation(self, doc: Document, note: str = "") -> Citation:
        return doc.line_citation(self.page, [self.line], note or self.key)


@dataclass
class Section:
    number: int
    title: str
    page: int
    start: int
    end: int  # exclusive

    def citation(self, doc: Document, note: str = "") -> Citation:
        return doc.line_citation(
            self.page, range(self.start, self.end), note or f"Section {self.number}, {self.title}"
        )


@dataclass
class ParsedDoc:
    doc: Document
    fields: Dict[str, Field]
    sections: List[Section]
    table: Table

    # ---- convenience -------------------------------------------------
    def field(self, *names: str) -> Optional[Field]:
        for name in names:
            for key, f in self.fields.items():
                if key.lower() == name.lower():
                    return f
        return None

    def section(self, keyword: str) -> Optional[Section]:
        for s in self.sections:
            if keyword.lower() in s.title.lower():
                return s
        return None

    def rows(self) -> Dict[str, Row]:
        return self.table.by_id()

    def test_ids(self) -> List[str]:
        return [r.text("test_id").upper() for r in self.table.rows]

    def bullets(self, section: Section) -> List[tuple[int, str]]:
        out = []
        lines = self.doc.pages[section.page - 1]
        for ln in range(section.start, section.end):
            m = BULLET.match(lines[ln - 1])
            if m:
                out.append((ln, squash(m.group(1))))
        return out

    def find_line(self, pattern: str) -> Optional[tuple[int, int]]:
        hits = self.doc.search(pattern)
        return (hits[0][0], hits[0][1]) if hits else None

    def cite_phrase(self, pattern: str, note: str = "") -> Optional[Citation]:
        """Cite the line(s) carrying a phrase. Sentences that wrap onto the
        next line are extended so the quote is not cut mid-sentence."""
        hits = self.doc.search(pattern)
        if not hits:
            return None
        page, ln, _ = hits[0]
        lines = self.doc.pages[page - 1]
        span_lines = [ln]
        if ln < len(lines) and not squash(lines[ln - 1]).endswith("."):
            nxt = squash(lines[ln])
            if nxt and not SECTION.match(lines[ln]) and not BULLET.match(lines[ln]):
                span_lines.append(ln + 1)
        return self.doc.line_citation(page, span_lines, note)


def _sections(doc: Document) -> List[Section]:
    found: List[Section] = []
    for page, ln, text in doc.iter_lines():
        m = SECTION.match(text)
        if m:
            found.append(Section(int(m.group(1)), squash(m.group(2)), page, ln, ln))
    for i, s in enumerate(found):
        page_len = len(doc.pages[s.page - 1])
        nxt = found[i + 1] if i + 1 < len(found) else None
        s.end = nxt.start if nxt and nxt.page == s.page else page_len + 1
    return found


def _fields(doc: Document) -> Dict[str, Field]:
    out: Dict[str, Field] = {}
    for page, ln, text in doc.iter_lines():
        if SECTION.match(text):
            break  # header block ends at the first numbered section
        m = HEADER_KV.match(text)
        if m:
            key = squash(m.group(1))
            out[key] = Field(key, squash(m.group(2)), page, ln)
    return out


def parse_document(doc: Document) -> ParsedDoc:
    return ParsedDoc(
        doc=doc,
        fields=_fields(doc),
        sections=_sections(doc),
        table=parse_table(doc),
    )


# ---- derived header facts ----------------------------------------------

def doc_id(parsed: ParsedDoc) -> Optional[str]:
    f = parsed.field("Document")
    if not f:
        return None
    m = DOC_ID.search(f.value)
    return m.group(1) if m else f.value


def version(parsed: ParsedDoc) -> Optional[str]:
    f = parsed.field("Version")
    if f:
        m = VERSION_REF.search(f.value) or re.search(r"([\d.]+)", f.value)
        return m.group(1) if m else None
    return None


def protocol_reference(parsed: ParsedDoc) -> tuple[Optional[str], Optional[str], Optional[Field]]:
    """(protocol doc id, protocol version, source field) as cited by a report."""
    f = parsed.field("Verifies protocol", "Protocol", "Reference protocol")
    if not f:
        return None, None, None
    doc_m = DOC_ID.search(f.value)
    ver_m = VERSION_REF.search(f.value)
    return (doc_m.group(1) if doc_m else None, ver_m.group(1) if ver_m else None, f)


def effective_date(parsed: ParsedDoc) -> tuple[Optional[date], Optional[Field]]:
    f = parsed.field("Effective", "Effective date")
    return (parse_date(f.value) if f else None), f


def report_date(parsed: ParsedDoc) -> tuple[Optional[date], Optional[Field]]:
    f = parsed.field("Date", "Report date")
    return (parse_date(f.value) if f else None), f


def equipment(parsed: ParsedDoc) -> tuple[Optional[str], Optional[date], Optional[Field]]:
    """(equipment text, calibration due date, source field)."""
    f = parsed.field("Test equipment", "Equipment")
    if not f:
        return None, None, None
    m = re.search(r"calibration\s+due\s+(.+?)(?:;|$)", f.value, re.I)
    return f.value, (parse_date(m.group(1)) if m else None), f
