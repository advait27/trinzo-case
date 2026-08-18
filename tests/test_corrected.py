"""The corrected pair.

These fixtures exist to prove a negative. The 16 findings on the original
documents only mean something if the same tool, unchanged, goes quiet on
documents that are consistent -- otherwise it could simply be a tool that
always fires.

The important assertions here are not "zero findings". They are that each
rule reached a real comparison and had nothing to raise. A parse failure
would also produce zero findings, and would be the worst possible way to
pass this test.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from protocolqc import extract as ex
from protocolqc.ingest import load_pdf
from protocolqc.limits import unchecked
from protocolqc.rules import run_rules
from protocolqc.verify import require_verified

from support import ROOT
from test_findings import EXPECTED

CORRECTED = ROOT / "corrected"
PROTOCOL = CORRECTED / "corrected-a-test-protocol-nv-200.pdf"
REPORT = CORRECTED / "corrected-b-verification-report-nv-200.pdf"


@unittest.skipUnless(PROTOCOL.exists() and REPORT.exists(),
                     "corrected fixtures not generated (run fixtures/make_corrected.py)")
class TestCorrectedPair(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol_doc = load_pdf(PROTOCOL, "protocol")
        cls.report_doc = load_pdf(REPORT, "report")
        cls.protocol = ex.parse_document(cls.protocol_doc)
        cls.report = ex.parse_document(cls.report_doc)
        cls.findings, cls.outcomes = run_rules(cls.protocol, cls.report)
        cls.by_rule = {o.rule_id: o for o in cls.outcomes}

    def test_no_findings(self):
        self.assertEqual(
            [(f.rule_id, f.scope, f.statement) for f in self.findings], []
        )

    def test_every_original_discrepancy_is_resolved(self):
        raised = {(f.rule_id, f.scope) for f in self.findings}
        for key, description in EXPECTED.items():
            with self.subTest(rule=key[0], scope=key[1]):
                self.assertNotIn(key, raised, f"still present: {description}")

    # ---- silence has to be earned, not the result of a parse failure ----

    def test_both_documents_parsed_completely(self):
        self.assertEqual(self.protocol.test_ids(), ["T1", "T2", "T3", "T4", "T5"])
        self.assertEqual(self.report.test_ids(), ["T1", "T2", "T3", "T4", "T5"])

    def test_no_rule_failed_to_reach_a_comparison(self):
        # R-17 is legitimately not applicable: it looks for undocumented
        # departures, and there are no departures to look for. Every other
        # rule must have compared something and found nothing.
        not_applicable = {r for r, o in self.by_rule.items() if o.status == "not-applicable"}
        self.assertEqual(not_applicable, {"R-17"})

    def test_the_substantive_comparisons_covered_every_test(self):
        self.assertIn("T1, T2, T3, T4, T5", self.by_rule["R-12"].detail)  # criteria
        self.assertIn("T1, T2, T3, T4, T5", self.by_rule["R-13"].detail)  # sample sizes
        self.assertIn("All 5 protocol tests", self.by_rule["R-10"].detail)  # coverage

    def test_numeric_results_were_compared_where_numbers_exist(self):
        # T4's criterion is qualitative, so it has no numeric comparison and
        # is covered by R-22 instead. The other four must have been compared.
        detail = self.by_rule["R-14"].detail
        for test_id in ("T1", "T2", "T3", "T5"):
            with self.subTest(test_id):
                self.assertIn(test_id, detail)
        self.assertIn("T4", self.by_rule["R-22"].detail)

    def test_calibration_and_dates_were_actually_checked(self):
        self.assertIn("31 Mar 2027", self.by_rule["R-04"].detail)
        self.assertIn("24 Jul 2026", self.by_rule["R-05"].detail)

    def test_blind_spots_are_still_published(self):
        # A clean run must still say what it did not check, or "no findings"
        # reads as "everything is fine".
        limits = unchecked(self.protocol, self.report)
        self.assertTrue(limits)
        self.assertTrue(any(l.scope == "T5" for l in limits))

    def test_citation_gate_runs_clean_on_an_empty_finding_set(self):
        result = require_verified(self.findings,
                                  {"protocol": self.protocol_doc, "report": self.report_doc})
        self.assertTrue(result.ok)

    # ---- the fixtures must still be capable of raising findings ----

    def test_the_fixture_is_not_simply_unparseable(self):
        """Break one value in the corrected report and the matching rule must
        fire. Without this, a fixture that failed to parse would pass every
        test above."""
        from support import layout_text, rebuild, replace_once, review, signature

        text = replace_once(layout_text(self.report_doc), "Min 5.3 N", "Min 4.3 N")
        raised = signature(review(self.protocol_doc, rebuild(self.report_doc, text)))
        self.assertIn(("R-14", "T1"), raised)
        self.assertIn(("R-15", "T1"), raised)

    def test_an_out_of_range_cytotoxicity_grade_is_caught(self):
        from support import layout_text, rebuild, replace_once, review, signature

        text = replace_once(layout_text(self.report_doc), "Reactivity grade 1",
                            "Reactivity grade 3")
        self.assertIn(("R-14", "T5"), signature(review(self.protocol_doc,
                                                       rebuild(self.report_doc, text))))


if __name__ == "__main__":
    unittest.main()
