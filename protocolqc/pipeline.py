"""One review, start to finish.

Extracted so the CLI and the upload server cannot drift apart: both call
review() and both get the same checks, the same citation gate and the same
outputs. A difference in behaviour between "I ran it on the command line" and
"I uploaded it" would be a serious problem in a regulated setting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from . import extract as ex
from .ai.client import AIUnavailable, NvidiaClient
from .ai.extract import ExtractionReport, parse_document as ai_parse_document
from .ai.suggest import suggest as ai_suggest
from .ingest import load_pdf
from .limits import Limit, unchecked
from .model import Document, Finding, RuleOutcome
from .quotes import QuoteRepairer
from .render import manifest
from .rules import RULESET_VERSION, run_rules
from .verify import VerificationResult, require_verified


@dataclass
class ReviewResult:
    findings: List[Finding]
    outcomes: List[RuleOutcome]
    limits: List[Limit]
    suggestions: List[Finding]
    manifest_data: dict
    docs: Dict[str, Document]
    doc_names: Dict[str, str]
    repairer: QuoteRepairer
    verification: VerificationResult
    ai_notes: List[str] = field(default_factory=list)


def review(protocol_path: str | Path, report_path: str | Path, *,
           ai_client: Optional[NvidiaClient] = None,
           want_suggestions: bool = False) -> ReviewResult:
    protocol_doc = load_pdf(protocol_path, "protocol")
    report_doc = load_pdf(report_path, "report")
    docs = {"protocol": protocol_doc, "report": report_doc}
    notes: List[str] = []

    # Deterministic parse first, model only where it is refused.
    protocol, protocol_report = ai_parse_document(protocol_doc, ai_client, is_report=False)
    report, report_report = ai_parse_document(report_doc, ai_client, is_report=True)
    for which, rep in (("protocol", protocol_report), ("report", report_report)):
        if rep.source == "ai-assisted":
            notes.append(
                f"{which}: layout not recognised, structure located by {rep.model} "
                f"({rep.tests_found} test rows, {rep.located} quotes found in the source, "
                f"{len(rep.discarded)} discarded as unverifiable)"
            )

    findings, outcomes = run_rules(protocol, report)
    limits = unchecked(protocol, report)

    suggestions: List[Finding] = []
    if want_suggestions and ai_client is not None:
        suggestions, sug_notes = ai_suggest(protocol, report, ai_client)
        notes.extend(sug_notes)

    # The gate covers model output exactly as it covers rule output. Anything
    # a model produced has already survived locate(); this re-checks it from
    # the source a second time, through the same code path.
    verification = require_verified(findings + suggestions, docs)

    manifest_data = manifest(docs, verification, RULESET_VERSION)
    manifest_data["extraction"] = {
        "protocol": protocol_report.as_dict(),
        "report": report_report.as_dict(),
    }
    manifest_data["ai"] = {
        "enabled": ai_client is not None,
        "model": ai_client.model if ai_client else None,
        "provider": "NVIDIA NIM" if ai_client else None,
        "suggestions_requested": bool(want_suggestions),
        "suggestions_kept": len(suggestions),
        "notes": notes,
        "boundary": (
            "A model is used only to locate text and to raise advisory points. "
            "It does not run the checks and it does not decide pass or fail. "
            "Every quotation it produced was found in the source document before "
            "being shown."
        ),
        "usage": {
            "calls": ai_client.usage.calls,
            "prompt_tokens": ai_client.usage.prompt_tokens,
            "completion_tokens": ai_client.usage.completion_tokens,
        } if ai_client else None,
    }

    return ReviewResult(
        findings=findings, outcomes=outcomes, limits=limits, suggestions=suggestions,
        manifest_data=manifest_data, docs=docs,
        doc_names={"protocol": protocol_doc.name, "report": report_doc.name},
        repairer=QuoteRepairer(docs), verification=verification, ai_notes=notes,
    )
