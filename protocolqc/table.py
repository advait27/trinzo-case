"""Recover the test table from layout-preserved text.

Column boundaries are found by looking for "gutters": character positions that
are blank on *every* line of the table block. Runs of two or more adjacent
gutter positions are treated as column separators. This is derived from the
document itself rather than from hard-coded offsets or from the header text,
so it survives a re-flowed or re-styled table.

If the structure does not look like the expected table, this module raises
instead of guessing. In a regulated setting a silently mis-parsed table is far
worse than a tool that refuses to run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .model import Citation, Document, Span, squash

SECTION_RE = re.compile(r"^\s{0,3}\d+\.\s+\S")
TEST_ID_RE = re.compile(r"^T\d+$", re.I)

# Header text -> canonical field name. Matching is on a normalised, lowercased
# header cell, so "Sample size" and "n tested" both land on `sample_size`.
COLUMN_ALIASES = {
    "test id": "test_id",
    "test": "test_name",
    "acceptance criterion": "criterion",
    "acceptance criteria": "criterion",
    "sample size": "sample_size",
    "n tested": "sample_size",
    "n": "sample_size",
    "method / conditions": "method",
    "method/conditions": "method",
    "method": "method",
    "result and disposition": "result",
    "result": "result",
}


class TableParseError(RuntimeError):
    """Raised when the table cannot be recovered with confidence."""


@dataclass
class Cell:
    parts: List[str] = field(default_factory=list)
    spans: List[Span] = field(default_factory=list)

    @property
    def text(self) -> str:
        """Cell contents with wrapped lines rejoined. A part ending in a
        hyphen between two alphanumerics is a mid-word PDF wrap
        ("Per ISO 10993-" + "5"), so it is joined without a space."""
        out = ""
        for part in self.parts:
            if not out:
                out = part
            elif re.search(r"[A-Za-z0-9]-$", out) and re.match(r"^[A-Za-z0-9]", part):
                out += part
            else:
                out += " " + part
        return squash(out)

    @property
    def empty(self) -> bool:
        return not self.text

    def citation(self, doc_key: str, note: str = "") -> Citation:
        return Citation(doc_key, list(self.spans), note)


@dataclass
class Row:
    cells: Dict[str, Cell]
    first_line: int

    def text(self, field_name: str) -> str:
        cell = self.cells.get(field_name)
        return cell.text if cell else ""

    def cell(self, field_name: str) -> Cell:
        return self.cells.get(field_name, Cell())


@dataclass
class Table:
    page: int
    header_line: int
    columns: List[Tuple[str, int, int]]  # (field name, start, end)
    rows: List[Row]

    @property
    def field_names(self) -> List[str]:
        return [c[0] for c in self.columns]

    def by_id(self) -> Dict[str, Row]:
        return {r.text("test_id").upper(): r for r in self.rows}


def _find_block(doc: Document, header_keyword: str) -> Tuple[int, int, int]:
    """Locate (page, header_line, end_line_exclusive) of the table block."""
    for page, line, text in doc.iter_lines():
        if header_keyword.lower() in text.lower():
            lines = doc.pages[page - 1]
            end = line  # 1-based index of header; scan forward
            i = line  # zero-based index of the line *after* the header
            while i < len(lines) and not SECTION_RE.match(lines[i]):
                i += 1
            end = i  # exclusive, 1-based -> lines[line-1 : end]
            while end > line and not lines[end - 1].strip():
                end -= 1
            return page, line, end
    raise TableParseError(
        f"{doc.name}: no table header containing {header_keyword!r} was found"
    )


def _gutters(lines: Sequence[str]) -> List[Tuple[int, int]]:
    """Column spans, derived from positions blank on every line."""
    body = [ln for ln in lines if ln.strip()]
    width = max(len(ln) for ln in body)
    padded = [ln.ljust(width) for ln in body]
    blank = [all(p[i] == " " for p in padded) for i in range(width)]

    separators: List[Tuple[int, int]] = []
    run_start: Optional[int] = None
    for i, is_blank in enumerate(blank + [False]):
        if is_blank and run_start is None:
            run_start = i
        elif not is_blank and run_start is not None:
            if i - run_start >= 2:
                separators.append((run_start, i))
            run_start = None

    spans: List[Tuple[int, int]] = []
    cursor = 0
    for sep_start, sep_end in separators:
        if sep_start > cursor:
            spans.append((cursor, sep_start))
        cursor = sep_end
    if cursor < width:
        spans.append((cursor, width))
    return spans


def parse_table(doc: Document, header_keyword: str = "Test ID") -> Table:
    page, header_line, end = _find_block(doc, header_keyword)
    lines = doc.pages[page - 1][header_line - 1 : end]
    if len(lines) < 2:
        raise TableParseError(f"{doc.name}: table block has no data rows")

    spans = _gutters(lines)
    header_raw = lines[0]
    columns: List[Tuple[str, int, int]] = []
    for start, stop in spans:
        label = squash(header_raw[start:stop])
        key = COLUMN_ALIASES.get(label.lower())
        if key is None:
            raise TableParseError(
                f"{doc.name}: unrecognised table column header {label!r} "
                f"(known: {sorted(set(COLUMN_ALIASES))})"
            )
        columns.append((key, start, stop))

    required = {"test_id", "criterion", "sample_size"}
    missing = required - {c[0] for c in columns}
    if missing:
        raise TableParseError(f"{doc.name}: table is missing column(s) {sorted(missing)}")

    id_span = next(c for c in columns if c[0] == "test_id")
    rows: List[Row] = []
    for offset, raw in enumerate(lines[1:], start=header_line + 1):
        if not raw.strip():
            continue
        id_text = squash(raw[id_span[1] : id_span[2]])
        if id_text and TEST_ID_RE.match(id_text):
            rows.append(Row(cells={name: Cell() for name, _, _ in columns},
                            first_line=offset))
        elif not rows:
            # Text before the first recognisable row: not part of any cell.
            continue
        row = rows[-1]
        for name, start, stop in columns:
            span = doc.trimmed_span(page, offset, start, stop)
            if span is None:
                continue
            cell = row.cells[name]
            cell.parts.append(span.text)
            cell.spans.append(span)

    if not rows:
        raise TableParseError(f"{doc.name}: table has a header but no T-numbered rows")
    return Table(page=page, header_line=header_line, columns=columns, rows=rows)
