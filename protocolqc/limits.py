"""What this tool did NOT check.

An empty findings list is not a pass, and the most dangerous failure mode for
a tool like this is a reviewer assuming the silence means "checked and fine".
So every run publishes its own blind spots alongside its findings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

from . import extract as ex
from .model import Citation
from .normalize import parse_criterion, Qualitative

EXTERNAL_REF = re.compile(r"\b(?:ISO|USP|IEC|EN|ASTM)\s*<?\d[\w\-<>.]*>?|\b[A-Z]{2,}-[A-Z0-9]+-\d+\b")


@dataclass
class Limit:
    scope: str
    item: str
    reason: str
    citation: Citation | None = None


def unchecked(protocol: ex.ParsedDoc, report: ex.ParsedDoc) -> List[Limit]:
    out: List[Limit] = []

    for tid in protocol.test_ids():
        row = protocol.rows()[tid]
        method = row.text("method")
        if method:
            out.append(Limit(
                tid,
                f"Method and conditions: \"{method}\"",
                "Read by the tool but only compared for stated temperature and named instrument. "
                "Everything else in this column needs a human to confirm against the report and "
                "the raw data.",
                row.cell("method").citation(protocol.doc.key, f"{tid} method / conditions"),
            ))
        for ref in set(EXTERNAL_REF.findall(" ".join([method, row.text("sample_size"), row.text("criterion")]))):
            out.append(Limit(
                tid,
                f"External reference: {ref}",
                "Not supplied to this tool. Conformity to it cannot be checked here.",
                row.cell("method").citation(protocol.doc.key, f"{tid} method / conditions"),
            ))
        if isinstance(parse_criterion(row.text("criterion")), Qualitative):
            out.append(Limit(
                tid,
                f"Qualitative criterion: \"{row.text('criterion')}\"",
                "No numeric comparison is possible. The tool checks only that quantified "
                "qualifiers are restated; the observation itself needs a human.",
                row.cell("criterion").citation(protocol.doc.key, f"{tid} acceptance criterion"),
            ))

    sampling = protocol.cite_phrase(r"sampling plan", "Section 2, General requirements")
    if sampling:
        out.append(Limit(
            "document",
            "The sampling plan referenced by the protocol",
            "Not supplied to this tool. Whether the units tested were drawn correctly cannot be checked here.",
            sampling,
        ))

    out.append(Limit(
        "document",
        "Raw data, test records and signatures",
        "This tool compares two documents only. It has not seen the underlying data, and cannot "
        "tell whether the numbers in the report reflect it.",
        None,
    ))
    out.append(Limit(
        "document",
        "Anything neither document states",
        "The tool can only compare text that is present. A requirement omitted from the protocol "
        "will not be checked against the report.",
        None,
    ))
    return out
