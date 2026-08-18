"""Citation integrity gate.

Every span attached to a finding is re-read from the source document and
compared, character for character, against what the finding claims is there.
Two independent checks are applied:

  1. Address check  -- doc[page][line][start:end] equals the recorded text.
  2. Presence check -- each span's text, whitespace-collapsed, occurs
                       somewhere in the whitespace-collapsed page text.

The second is redundant while the first passes, and that is the point: it is a
second, differently-implemented route to the same conclusion, so a bug in the
addressing code cannot quietly let invented text through both.

The check is per span, not per assembled quote. A citation may legitimately
gather spans that are not contiguous in the source -- a table cell that wraps
across two lines has other columns' text between the pieces -- so requiring
the joined quote to appear verbatim would reject correct citations.

If any citation fails, the run is aborted and no output is written. A review
sheet with one invented quote in it is worse than no review sheet, because it
teaches the reviewer to trust the rest.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List

from .model import Citation, Document, Finding


class CitationError(RuntimeError):
    pass


@dataclass
class VerificationResult:
    spans_checked: int
    citations_checked: int
    failures: List[str]

    @property
    def ok(self) -> bool:
        return not self.failures


def _page_text(doc: Document, page: int) -> str:
    return re.sub(r"\s+", " ", "\n".join(doc.pages[page - 1]))


def verify_citations(findings: Iterable[Finding], docs: Dict[str, Document]) -> VerificationResult:
    failures: List[str] = []
    spans = citations = 0

    for finding in findings:
        for cite in finding.citations:
            citations += 1
            doc = docs.get(cite.doc)
            if doc is None:
                failures.append(f"{finding.id}: citation names unknown document {cite.doc!r}")
                continue
            if not cite.spans:
                failures.append(f"{finding.id}: citation carries no spans")
                continue

            for span in cite.spans:
                spans += 1
                if span.doc != cite.doc:
                    failures.append(
                        f"{finding.id}: span document {span.doc!r} does not match citation {cite.doc!r}")
                    continue
                try:
                    actual = doc.slice(span.page, span.line, span.start, span.end)
                except IndexError:
                    failures.append(
                        f"{finding.id}: {cite.doc} p.{span.page} line {span.line} does not exist")
                    continue
                if actual != span.text:
                    failures.append(
                        f"{finding.id}: {cite.doc} p.{span.page} line {span.line} "
                        f"cols {span.start}-{span.end} holds {actual!r}, citation claims {span.text!r}")
                    continue

                fragment = re.sub(r"\s+", " ", span.text).strip()
                if fragment and fragment not in _page_text(doc, span.page):
                    failures.append(
                        f"{finding.id}: quoted text {fragment!r} does not occur on "
                        f"{cite.doc} p.{span.page}")

    return VerificationResult(spans, citations, failures)


def require_verified(findings: Iterable[Finding], docs: Dict[str, Document]) -> VerificationResult:
    result = verify_citations(findings, docs)
    if not result.ok:
        raise CitationError(
            "Citation verification failed; no output written.\n  - "
            + "\n  - ".join(result.failures)
        )
    return result
