"""Outputs: a JSON record for the audit trail, and an HTML sheet for the
reviewer.

The HTML is written for someone who is expert in QA and not in software. It
leads with what the tool is not allowed to do, shows both sides of every flag
with a locator the reviewer can look up in the PDF, and gives them somewhere
to record their own decision -- which is the only decision that counts.

The sheet's interface lives in ui/ (React + Framer Motion) and is built into
protocolqc/assets/. This module inlines those assets and the findings data
into a single self-contained file; see the note above to_html.
"""

from __future__ import annotations

import html
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from .limits import Limit
from .model import Citation, Document, Finding, RuleOutcome
from .quotes import NullRepairer, QuoteRepairer
from .verify import VerificationResult

TOOL_NAME = "protocolqc"
TOOL_VERSION = "0.3.0"

DISCLAIMER = (
    "Decision support only. This tool does not determine pass or fail, and its output is not a "
    "validated record. It reports differences between two documents, with a citation to the exact "
    "text behind each one, for a qualified reviewer to judge."
)

SILENCE = (
    "An empty result is not a pass. It means these checks found nothing to raise. "
    "See \"What was not checked\"."
)


def manifest(docs: Dict[str, Document], verification: VerificationResult,
             ruleset_version: str, run_at: str | None = None) -> dict:
    return {
        "tool": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        "ruleset_version": ruleset_version,
        "run_at_utc": run_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "documents": {
            key: {
                "name": doc.name,
                "path": doc.path,
                "file_sha256": doc.file_sha256,
                "extracted_text_sha256": doc.text_sha256,
                "pages": len(doc.pages),
            }
            for key, doc in docs.items()
        },
        "citation_verification": {
            "citations_checked": verification.citations_checked,
            "spans_checked": verification.spans_checked,
            "failures": verification.failures,
            "passed": verification.ok,
        },
        "boundary": DISCLAIMER,
    }


def _citation_json(c: Citation, repairer: QuoteRepairer) -> dict:
    """`quote` is exactly what the cited spans hold. `quote_display` is the
    same text with layout-artefact spaces closed (see quotes.py); it is what
    the reviewer sees. Both are recorded so the two can always be compared."""
    raw = c.quote
    display = repairer.quote(c)
    return {
        "document": c.doc,
        "note": c.note,
        "locator": c.locator,
        "quote": raw,
        "quote_display": display,
        "display_differs_from_source": display != raw,
        "spans": [asdict(s) for s in c.spans],
    }


def _finding_json(f: Finding, repairer: QuoteRepairer) -> dict:
    return {
        "id": f.id,
        "rule_id": f.rule_id,
        "rule_title": f.rule_title,
        "category": f.category,
        "review_priority": f.priority,
        "scope": f.scope,
        "observation": f.statement,
        "basis": f.basis,
        "reviewer_action": f.reviewer_action,
        "uncertainty": f.uncertainty,
        "source": f.source,
        "citations": [_citation_json(c, repairer) for c in f.citations],
    }


def to_json(findings: List[Finding], outcomes: List[RuleOutcome],
            limits: List[Limit], manifest_data: dict,
            repairer: QuoteRepairer | None = None,
            suggestions: List[Finding] | None = None) -> str:
    repairer = repairer or NullRepairer()
    payload = {
        "manifest": manifest_data,
        "findings": [_finding_json(f, repairer) for f in findings],
        # Advisory model output. Kept in its own key so nothing downstream can
        # accidentally treat a suggestion as a check result.
        "ai_suggestions": [_finding_json(f, repairer) for f in (suggestions or [])],
        "rules_run": [asdict(o) for o in outcomes],
        "not_checked": [
            {
                "scope": l.scope,
                "item": l.item,
                "reason": l.reason,
                "citation": _citation_json(l.citation, repairer) if l.citation else None,
            }
            for l in limits
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


# ---- HTML ---------------------------------------------------------------
#
# The reviewer's sheet is a React + Framer Motion app, built from ui/ and
# committed to protocolqc/assets/. It is inlined here -- script, styles and
# data in one file -- because the sheet has to open from a file:// path on a
# machine with no network. Nothing is fetched at runtime and there is no CDN.
#
# Rebuild the assets with:  cd ui && node build.mjs

ASSETS = Path(__file__).resolve().parent / "assets"


class AssetsMissing(RuntimeError):
    pass


def _asset(name: str) -> str:
    path = ASSETS / name
    if not path.exists():
        raise AssetsMissing(
            f"{path} is missing. Build the review sheet UI with:\n"
            f"    cd ui && npm install && node build.mjs"
        )
    return path.read_text(encoding="utf-8")


def _embed_json(payload: str) -> str:
    """Escape a JSON string for safe inclusion in a <script> block. Escaping
    '<' as \u003c is valid JSON and makes '</script>' unrepresentable, so the
    document text can never terminate the tag early."""
    return payload.replace("<", "\\u003c")


def to_html(findings: List[Finding], outcomes: List[RuleOutcome],
            limits: List[Limit], manifest_data: dict, doc_names: Dict[str, str],
            repairer: QuoteRepairer | None = None,
            suggestions: List[Finding] | None = None) -> str:
    repairer = repairer or NullRepairer()
    payload = to_json(findings, outcomes, limits, manifest_data, repairer, suggestions)
    counts = {p: sum(1 for f in findings if f.priority == p) for p in ("high", "medium", "low")}
    title = f"Review sheet — {doc_names.get('protocol', 'protocol')} vs {doc_names.get('report', 'report')}"

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{html.escape(title)}</title>
<style>{_asset("review-app.css")}</style>
</head>
<body>
<div id="root"></div>

<noscript>
  <div style="max-width:64ch;margin:56px auto;padding:0 24px;font:15px/1.6 system-ui,sans-serif">
    <h1 style="font-size:19px">This review sheet needs JavaScript</h1>
    <p>It found <strong>{len(findings)}</strong> item(s) for review
       ({counts['high']} high, {counts['medium']} medium, {counts['low']} low priority)
       in <code>{html.escape(doc_names.get('report', 'the report'))}</code>
       against <code>{html.escape(doc_names.get('protocol', 'the protocol'))}</code>.</p>
    <p>Every finding, with its citations and character offsets, is also written to
       <code>findings.json</code> beside this file. That file is the audit record and
       needs no browser at all.</p>
    <p><strong>This tool does not determine pass or fail.</strong> A qualified reviewer does.</p>
  </div>
</noscript>

<script type="application/json" id="review-data">{_embed_json(payload)}</script>
<script>{_asset("review-app.js")}</script>
</body>
</html>"""
