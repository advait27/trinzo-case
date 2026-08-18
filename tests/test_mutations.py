"""Mutation tests.

A rule that only ever fires on one known pair of documents proves nothing --
it could be a hard-coded answer. Each test here changes the source text and
asserts the rules respond to the change: findings that should disappear
disappear, and findings that should appear on a clean test appear.

Every mutation is applied to text extracted from the real PDFs and re-run
through the real parser, so the whole pipeline is under test, not just the
rule function.
"""

from __future__ import annotations

import unittest

from support import (
    drop_lines,
    layout_text,
    load_docs,
    rebuild,
    replace_once,
    review,
    signature,
)


class TestMutations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol_doc, cls.report_doc = load_docs()
        cls.protocol_text = layout_text(cls.protocol_doc)
        cls.report_text = layout_text(cls.report_doc)
        cls.baseline = signature(review(cls.protocol_doc, cls.report_doc))

    def with_report(self, text):
        return signature(review(self.protocol_doc, rebuild(self.report_doc, text)))

    def with_protocol(self, text):
        return signature(review(rebuild(self.protocol_doc, text), self.report_doc))

    # ---- findings that should go away when the defect is fixed -----

    def test_correcting_the_protocol_version_silences_r01(self):
        text = replace_once(self.report_text, "NV-200-TP-014, Version 1.0",
                            "NV-200-TP-014, Version 2.0")
        self.assertNotIn(("R-01", "document"), self.with_report(text))

    def test_in_date_calibration_silences_r04(self):
        text = replace_once(self.report_text, "calibration due 30 June 2025",
                            "calibration due 30 June 2027")
        self.assertNotIn(("R-04", "document"), self.with_report(text))

    def test_stating_the_test_date_silences_r06(self):
        text = replace_once(self.report_text, "1. Summary",
                            "Testing performed: 20 - 24 June 2026\n\n1. Summary")
        self.assertNotIn(("R-06", "document"), self.with_report(text))

    def test_documenting_a_deviation_silences_r17(self):
        text = replace_once(
            self.report_text,
            "1. Summary",
            "1. Summary\nDeviation DEV-014-1: sample size reduced to 25, justified below.",
        )
        result = self.with_report(text)
        self.assertNotIn(("R-17", "document"), result)
        # The departures themselves must still be reported -- documenting a
        # deviation does not make the sample size shortfall disappear.
        self.assertIn(("R-13", "T1"), result)

    def test_reporting_t5_silences_r10_and_r21(self):
        text = replace_once(
            self.report_text,
            " T4             Corrosion resistance                  No visible corrosion at 24 h        10              No corrosion observed. Pass.",
            " T4             Corrosion resistance                  No visible corrosion at 24 h        10              No corrosion observed. Pass.\n"
            " T5             Cytotoxicity (biocompatibility)       Reactivity grade <= 2               6               Grade 1 observed. Pass.",
        )
        result = self.with_report(text)
        self.assertNotIn(("R-10", "T5"), result)

    def test_restoring_the_conditions_silences_r16(self):
        text = replace_once(self.report_text, "Tested at ambient", "Tested in 37°C saline")
        result = self.with_report(text)
        self.assertNotIn(("R-16", "T1"), result)
        self.assertIn(("R-14", "T1"), result)  # the low result is unaffected

    def test_correct_sample_size_silences_r13(self):
        text = replace_once(self.report_text,
                            "≥ 4.5 N                             25",
                            "≥ 4.5 N                             30")
        self.assertNotIn(("R-13", "T1"), self.with_report(text))

    # ---- the critical one: comparison must use the PROTOCOL -------

    def test_results_are_judged_against_the_protocol_not_the_report(self):
        """If the protocol itself said >= 4.5 N, the reported 4.7 N minimum
        would be inside the criterion and R-14 should fall silent for T1. This
        is what proves R-14 reads the protocol's figure and not the weakened
        one the report prints for itself."""
        text = replace_once(self.protocol_text, "≥ 5.0 N", "≥ 4.5 N")
        result = self.with_protocol(text)
        self.assertNotIn(("R-14", "T1"), result)
        self.assertNotIn(("R-12", "T1"), result)  # criteria now agree
        self.assertNotIn(("R-15", "T1"), result)  # nothing left to contradict
        self.assertIn(("R-13", "T1"), result)  # sample size still short

    # ---- findings that should appear on a currently clean test ----

    def test_an_out_of_spec_t2_result_is_caught(self):
        # T2 raises nothing today. Push its result past the criterion and both
        # the value check and the disposition check must fire on it.
        text = replace_once(self.report_text, "Max 12 particles", "Max 32 particles")
        result = self.with_report(text)
        self.assertIn(("R-14", "T2"), result)
        self.assertIn(("R-15", "T2"), result)

    def test_an_undersampled_t2_is_caught(self):
        text = replace_once(self.report_text,
                            "≥10 µm per           30",
                            "≥10 µm per           10")
        self.assertIn(("R-13", "T2"), self.with_report(text))

    def test_a_test_not_in_the_protocol_is_caught(self):
        # Renumber the protocol's T4 so the report's T4 becomes unplanned.
        text = replace_once(self.protocol_text, " T4              Corrosion",
                            " T9              Corrosion")
        result = self.with_protocol(text)
        self.assertIn(("R-11", "T4"), result)
        self.assertIn(("R-10", "T9"), result)

    def test_a_wrong_protocol_number_is_caught(self):
        text = replace_once(self.report_text, "Verifies protocol:  NV-200-TP-014",
                            "Verifies protocol:  NV-201-TP-014")
        self.assertIn(("R-02", "document"), self.with_report(text))

    def test_missing_instrument_is_caught(self):
        text = replace_once(self.report_text, "Instron 5943 (serial 5943       -11)",
                            "Zwick 1120 (serial 1120-04)     ")
        self.assertIn(("R-19", "T1"), self.with_report(text))

    def test_testing_before_the_protocol_was_effective_is_caught(self):
        text = replace_once(self.report_text, "Date:  3 July 2026", "Date:  3 March 2026")
        self.assertIn(("R-05", "document"), self.with_report(text))

    def test_removing_t5_from_the_protocol_removes_its_findings(self):
        text = drop_lines(
            drop_lines(self.protocol_text, "Cytotoxicity"), "report BC-NV200-03"
        )
        result = self.with_protocol(text)
        self.assertNotIn(("R-10", "T5"), result)
        self.assertNotIn(("R-18", "T5"), result)

    def test_baseline_is_unchanged_by_all_of_the_above(self):
        # Mutations operate on copies; the real run must still be intact.
        self.assertEqual(signature(review(self.protocol_doc, self.report_doc)), self.baseline)


if __name__ == "__main__":
    unittest.main()
