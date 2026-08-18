"""LLM-assisted extraction, for documents the parser does not recognise.

The deterministic parser handles the template family it was built for and
raises rather than guess at anything else. That is right for a known corpus
and useless for a document a user has just uploaded.

This module fills that gap without moving any judgement into the model. The
model proposes where things are; locate.py finds that text in the document and
builds the offsets; the result is an ordinary ParsedDoc. rules.py neither knows
nor cares that it came from a model -- the checks, the citations and the
verification gate are identical either way.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .. import extract as ex
from ..model import Document, Span
from ..table import Cell, Row, Table
from .client import AIUnavailable, NvidiaClient
from .locate import LocateStats, locate, locate_all, numbered
from .prompts import EXTRACT_SYSTEM, EXTRACT_USER

FIELD_KEYS = {
    "document": "Document",
    "title": "Title",
    "version": "Version",
    "effective": "Effective",
    "date": "Date",
    "verifies protocol": "Verifies protocol",
    "test equipment": "Test equipment",
    "revision": "Revision",
    "testing performed": "Testing performed",
}
CELL_KEYS = ("test_id", "test_name", "criterion", "sample_size", "method", "result")


@dataclass
class ExtractionReport:
    """Provenance for one document, carried into the manifest so a reader can
    always tell which parts of a run a model touched."""

    source: str = "deterministic"          # "deterministic" | "ai-assisted"
    model: Optional[str] = None
    reason: str = ""
    fields_found: int = 0
    tests_found: int = 0
    located: int = 0
    line_hint_wrong: int = 0
    discarded: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "model": self.model,
            "reason": self.reason,
            "fields_found": self.fields_found,
            "tests_found": self.tests_found,
            "quotes_located_in_source": self.located,
            "line_hints_corrected": self.line_hint_wrong,
            "discarded_unverifiable": self.discarded,
        }


def _loads(raw: str) -> Dict[str, Any]:
    """Parse the model's reply. Tolerates a fenced block or surrounding chatter
    -- but never repairs the JSON itself."""
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        brace = re.search(r"\{.*\}", text, re.S)
        if not brace:
            raise AIUnavailable("model did not return JSON")
        try:
            return json.loads(brace.group(0))
        except json.JSONDecodeError as exc:
            raise AIUnavailable(f"model returned malformed JSON: {exc}") from exc


def _cell(doc: Document, value: str, line: Optional[int], stats: LocateStats,
          what: str) -> Optional[Cell]:
    spans = locate_all(doc, value, line, 1, stats, what)
    if not spans:
        return None
    return Cell(parts=[s.text for s in spans], spans=spans)


def parse_with_ai(doc: Document, client: NvidiaClient, *, is_report: bool,
                  reason: str) -> tuple[ex.ParsedDoc, ExtractionReport]:
    kind = "verification report" if is_report else "test protocol"
    result_key = "result" if is_report else "method"

    reply = client.complete(
        EXTRACT_SYSTEM,
        EXTRACT_USER.format(kind=kind, result_key=result_key, text=numbered(doc)),
    )
    data = _loads(reply)
    stats = LocateStats()
    report = ExtractionReport(source="ai-assisted", model=client.model, reason=reason)

    # ---- header fields ------------------------------------------------
    fields: Dict[str, ex.Field] = {}
    for item in data.get("fields") or []:
        key = str(item.get("key", "")).strip().lower()
        value = str(item.get("value", "")).strip()
        if key not in FIELD_KEYS or not value:
            continue
        span = locate(doc, value, item.get("line"), 1, stats, f"field {key}")
        if span is None:
            continue                      # unverifiable -> dropped, not guessed
        label = FIELD_KEYS[key]
        fields[label] = ex.Field(label, span.text, span.page, span.line)

    # ---- sections -----------------------------------------------------
    sections: List[ex.Section] = []
    for item in data.get("sections") or []:
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        span = locate(doc, title, item.get("line"), 1, stats, "section")
        if span is None:
            continue
        try:
            number = int(item.get("number") or len(sections) + 1)
        except (TypeError, ValueError):
            number = len(sections) + 1
        sections.append(ex.Section(number, span.text, span.page, span.line, span.line))
    page_len = len(doc.pages[0])
    for i, s in enumerate(sections):
        s.end = sections[i + 1].start if i + 1 < len(sections) else page_len + 1

    # ---- test table ---------------------------------------------------
    rows: List[Row] = []
    present: List[str] = []
    for item in data.get("tests") or []:
        cells: Dict[str, Cell] = {}
        first_line = 0
        for key in CELL_KEYS:
            raw = item.get(key)
            if not isinstance(raw, dict):
                continue
            value = str(raw.get("value", "")).strip()
            if not value:
                continue
            cell = _cell(doc, value, raw.get("line"), stats, f"{key}")
            if cell is None:
                continue
            cells[key] = cell
            if key not in present:
                present.append(key)
            if key == "test_id":
                first_line = cell.spans[0].line
        # A row with no verifiable test id cannot be joined to anything.
        if "test_id" not in cells:
            continue
        rows.append(Row(cells=cells, first_line=first_line))

    columns = [(k, 0, 0) for k in CELL_KEYS if k in present]
    header_line = min((r.first_line for r in rows), default=1)
    table = Table(page=1, header_line=header_line, columns=columns, rows=rows)

    report.fields_found = len(fields)
    report.tests_found = len(rows)
    report.located = stats.located
    report.line_hint_wrong = stats.line_hint_wrong
    report.discarded = stats.discarded
    return ex.ParsedDoc(doc=doc, fields=fields, sections=sections, table=table), report


def parse_document(doc: Document, client: Optional[NvidiaClient], *, is_report: bool
                   ) -> tuple[ex.ParsedDoc, ExtractionReport]:
    """Deterministic parse, with the model as a fallback and never as a first
    resort. The deterministic path is cheaper, reproducible and auditable; it
    is only abandoned when it refuses the document outright."""
    from ..table import TableParseError

    try:
        return ex.parse_document(doc), ExtractionReport()
    except TableParseError as exc:
        if client is None:
            raise
        return parse_with_ai(doc, client, is_report=is_report,
                             reason=f"deterministic parser declined this document: {exc}")
