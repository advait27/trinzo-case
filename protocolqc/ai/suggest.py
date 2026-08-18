"""Advisory observations from a model, for differences the rules do not model.

R-16 compares stated temperature and named instrument and nothing else; the
rest of a method column goes into "not checked". This is an attempt to narrow
that gap without pretending the result is a check.

Three properties keep it honest:

  * Suggestions never enter the findings list. They travel in their own
    bucket, are labelled with the model that produced them, and are shown
    under their own heading with their own caveat.
  * Every quote goes through locate() and then through verify.py, exactly like
    a rule citation. A suggestion whose quotes cannot be found in the source
    is dropped entirely rather than shown without evidence.
  * The prompt forbids pass/fail language and forbids re-reporting anything
    the deterministic rules already cover.

A suggestion is a prompt to go and look. It is not a finding, and the output
says so wherever it appears.
"""

from __future__ import annotations

import re
from typing import List, Optional

from .. import extract as ex
from ..model import Citation, Document, Finding
from .client import AIUnavailable, NvidiaClient
from .extract import _loads
from .locate import LocateStats, locate_all, numbered
from .prompts import SUGGEST_SYSTEM, SUGGEST_USER

MAX_SUGGESTIONS = 6
# Deliberately broad, and prefix-based rather than an exact word list: an
# earlier version missed "fails" because \b would not match after "fail".
# Over-blocking costs a suggestion and is recorded in the notes; under-blocking
# puts an adjudication in front of a reviewer, which is the failure that matters.
VERDICT_WORDS = re.compile(
    r"\b(?:pass|fail|conform|non-?conform|complian|acceptab|unacceptab|"
    r"approv|reject|satisf)\w*",
    re.I,
)


def suggest(protocol: ex.ParsedDoc, report: ex.ParsedDoc, client: NvidiaClient,
            limit: int = MAX_SUGGESTIONS) -> tuple[List[Finding], List[str]]:
    """Returns (suggestions, notes). Never raises for model problems -- an
    advisory extra must not be able to break a review."""
    notes: List[str] = []
    try:
        reply = client.complete(
            SUGGEST_SYSTEM,
            SUGGEST_USER.format(
                protocol_name=protocol.doc.name, report_name=report.doc.name,
                protocol=numbered(protocol.doc), report=numbered(report.doc),
                limit=limit,
            ),
        )
        data = _loads(reply)
    except AIUnavailable as exc:
        return [], [f"AI suggestions unavailable: {exc}"]

    stats = LocateStats()
    docs = {"protocol": protocol.doc, "report": report.doc}
    out: List[Finding] = []

    for i, item in enumerate(data.get("suggestions") or [], start=1):
        if len(out) >= limit:
            break
        observation = str(item.get("observation", "")).strip()
        if not observation:
            continue

        # The prompt forbids verdict language; this enforces it rather than
        # trusting it. A suggestion that adjudicates is dropped, not reworded.
        if VERDICT_WORDS.search(observation):
            notes.append(
                f"suggestion {i} dropped: it used pass/fail language "
                f"({VERDICT_WORDS.search(observation).group(0)!r})"
            )
            continue

        citations: List[Citation] = []
        for key, doc in (("protocol", protocol.doc), ("report", report.doc)):
            quote = str(item.get(f"{key}_quote", "")).strip()
            if not quote:
                continue
            spans = locate_all(doc, quote, item.get(f"{key}_line"), 1, stats,
                               f"suggestion {i} {key} quote")
            if spans:
                citations.append(Citation(key, spans, "AI-located quote"))

        if not citations:
            notes.append(f"suggestion {i} dropped: no quote could be found in either document")
            continue

        scope = str(item.get("scope", "document")).strip() or "document"
        if not re.fullmatch(r"T\d+|document", scope, re.I):
            scope = "document"

        out.append(Finding(
            id="",
            rule_id="AI",
            rule_title="Model-suggested difference (not a rule)",
            category="ai-suggestion",
            priority="low",
            scope=scope.upper() if scope.lower().startswith("t") else "document",
            statement=observation,
            basis=(
                "Suggested by a language model, not produced by a check. It is "
                "listed because the rule set does not model this kind of difference."
            ),
            reviewer_action=str(item.get("reviewer_action", "")).strip()
                            or "Read both quoted passages and decide whether this matters.",
            citations=citations,
            uncertainty=(
                "Model output. It may be wrong, incomplete, or unimportant. The quotes "
                "below were found in the source documents, but the point being made about "
                "them was not verified by anything."
            ),
            source="ai-suggested",
        ))

    for i, f in enumerate(out, start=1):
        f.id = f"AI-{i:03d}"
    if stats.discarded:
        notes.extend(stats.discarded)
    return out, notes
