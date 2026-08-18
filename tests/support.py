"""Shared test helpers.

Mutation tests work on the extracted *text* of the real PDFs rather than on
hand-written fixtures. That keeps them honest: they exercise the same parsing
and rule code as a real run, on text that genuinely came out of these files.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from protocolqc import extract as ex
from protocolqc.ingest import load_pdf
from protocolqc.model import Document, Finding
from protocolqc.rules import run_rules

ROOT = Path(__file__).resolve().parent.parent
PROTOCOL_PDF = ROOT / "sample-a-test-protocol-nv-200.pdf"
REPORT_PDF = ROOT / "sample-b-verification-report-nv-200.pdf"


def load_docs() -> Tuple[Document, Document]:
    return load_pdf(PROTOCOL_PDF, "protocol"), load_pdf(REPORT_PDF, "report")


def layout_text(doc: Document) -> str:
    return "\n".join(doc.pages[0])


def rebuild(doc: Document, text: str) -> Document:
    return Document.from_text(doc.key, doc.name, text)


def review(protocol: Document, report: Document) -> List[Finding]:
    findings, _ = run_rules(ex.parse_document(protocol), ex.parse_document(report))
    return findings


def signature(findings: List[Finding]) -> set[Tuple[str, str]]:
    """(rule id, scope) pairs -- what fired and where."""
    return {(f.rule_id, f.scope) for f in findings}


def replace_once(text: str, old: str, new: str) -> str:
    """String replacement that fails loudly if the target is not unique, so a
    mutation test can never silently mutate nothing."""
    count = text.count(old)
    if count != 1:
        raise AssertionError(f"expected exactly one occurrence of {old!r}, found {count}")
    return text.replace(old, new)


def drop_lines(text: str, containing: str) -> str:
    kept = [ln for ln in text.split("\n") if containing not in ln]
    if len(kept) == len(text.split("\n")):
        raise AssertionError(f"no lines contained {containing!r}")
    return "\n".join(kept)
