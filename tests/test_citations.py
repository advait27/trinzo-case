"""Citation integrity -- the check that every quote is real text.

These are the tests that matter most. A wrong finding wastes a reviewer's
time; an invented quote destroys their ability to trust any of it.
"""

from __future__ import annotations

import re
import unittest
from dataclasses import replace

from protocolqc import extract as ex
from protocolqc.model import Citation
from protocolqc.rules import run_rules
from protocolqc.verify import CitationError, require_verified, verify_citations

from support import load_docs


class TestCitations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol_doc, cls.report_doc = load_docs()
        cls.docs = {"protocol": cls.protocol_doc, "report": cls.report_doc}
        cls.findings, _ = run_rules(
            ex.parse_document(cls.protocol_doc), ex.parse_document(cls.report_doc)
        )

    def test_every_finding_carries_evidence(self):
        for f in self.findings:
            with self.subTest(f.id):
                self.assertTrue(f.citations, f"{f.id} has no citation")
                for c in f.citations:
                    self.assertTrue(c.spans, f"{f.id} has an empty citation")

    def test_every_span_matches_the_source_character_for_character(self):
        result = verify_citations(self.findings, self.docs)
        self.assertEqual(result.failures, [])
        self.assertGreater(result.spans_checked, 40)

    def test_every_quote_occurs_in_the_source_page(self):
        # Independent of the addressing logic: collapse whitespace and look
        # the text up in the page.
        for f in self.findings:
            for c in f.citations:
                for span in c.spans:
                    page = re.sub(r"\s+", " ", "\n".join(self.docs[c.doc].pages[span.page - 1]))
                    fragment = re.sub(r"\s+", " ", span.text).strip()
                    with self.subTest(finding=f.id, fragment=fragment):
                        self.assertIn(fragment, page)

    def test_comparison_findings_cite_both_documents(self):
        # Anything that asserts a difference between the documents has to show
        # the reviewer both sides of it.
        both_sided = {"R-01", "R-12", "R-13", "R-14", "R-15", "R-16", "R-22"}
        for f in self.findings:
            if f.rule_id in both_sided:
                with self.subTest(f.id):
                    self.assertEqual(
                        {c.doc for c in f.citations},
                        {"protocol", "report"},
                        f"{f.id} ({f.rule_id}) does not cite both documents",
                    )

    # ---- the gate must actually reject bad citations ---------------

    def test_fabricated_quote_is_rejected(self):
        # A plausible sentence that appears in neither document, attached to a
        # real address -- the shape a hallucinated citation would take.
        f = self.findings[0]
        span = f.citations[0].spans[0]
        forged = replace(span, text="the device met all acceptance criteria")
        tampered = list(self.findings)
        tampered[0] = _with_citations(f, [Citation(span.doc, [forged])])
        with self.assertRaises(CitationError):
            require_verified(tampered, self.docs)

    def test_text_recorded_against_the_wrong_address_is_rejected(self):
        # Real text from the document, but pointing at the wrong line: the
        # address check catches it even though the words exist somewhere.
        f = self.findings[0]
        span = f.citations[0].spans[0]
        misaddressed = replace(span, line=span.line + 3)
        tampered = list(self.findings)
        tampered[0] = _with_citations(f, [Citation(span.doc, [misaddressed])])
        with self.assertRaises(CitationError):
            require_verified(tampered, self.docs)

    def test_citation_to_a_nonexistent_document_is_rejected(self):
        f = self.findings[0]
        span = f.citations[0].spans[0]
        tampered = list(self.findings)
        tampered[0] = _with_citations(f, [Citation("appendix-c", [span])])
        with self.assertRaises(CitationError):
            require_verified(tampered, self.docs)

    def test_clean_run_passes_the_gate(self):
        result = require_verified(self.findings, self.docs)
        self.assertTrue(result.ok)


def _with_citations(finding, citations):
    clone = replace(finding)
    clone.citations = citations
    return clone


if __name__ == "__main__":
    unittest.main()
