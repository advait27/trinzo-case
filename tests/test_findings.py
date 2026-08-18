"""Ground truth for the two sample documents.

The expected set below was built by reading both PDFs by hand and listing the
discrepancies, before the rules were written to catch them. It is the
regression net: if a change to parsing or a rule drops one of these, or starts
flagging T2, the suite fails.
"""

from __future__ import annotations

import unittest

from protocolqc import extract as ex
from protocolqc.rules import run_rules

from support import load_docs, review, signature

# (rule, scope) -> what a human reviewer would call it
EXPECTED = {
    ("R-01", "document"): "report verifies protocol v1.0; protocol supplied is v2.0",
    ("R-04", "document"): "instrument calibration due 30 Jun 2025, report dated 3 Jul 2026",
    ("R-06", "document"): "no date of testing stated anywhere in the report",
    ("R-10", "T5"): "cytotoxicity required by the protocol, absent from the report",
    ("R-12", "T1"): "report restates the criterion as >= 4.5 N; protocol says >= 5.0 N",
    ("R-13", "T1"): "25 units tested; protocol requires 30",
    ("R-14", "T1"): "reported minimum 4.7 N is below the protocol's >= 5.0 N",
    ("R-14", "T3"): "reported 0.45 N is above the protocol's 0.20-0.40 N range",
    ("R-15", "T1"): "recorded as Pass while its own values sit outside the criterion",
    ("R-15", "T3"): "recorded as Pass while its own values sit outside the criterion",
    ("R-16", "T1"): "tested at ambient; protocol requires a 37 C saline bath",
    ("R-17", "document"): "departures present but no deviation documented",
    ("R-18", "T5"): "protocol gives no numeric sample size for T5",
    ("R-20", "document"): "summary claims all tests met their criteria",
    ("R-21", "document"): "conclusion recommends release with T5 unreported",
    ("R-22", "T4"): "'at 24 h' in the criterion is not restated in the result",
}


class TestFindings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol_doc, cls.report_doc = load_docs()
        cls.findings = review(cls.protocol_doc, cls.report_doc)
        cls.sig = signature(cls.findings)

    def test_every_known_discrepancy_is_found(self):
        for key, description in EXPECTED.items():
            with self.subTest(rule=key[0], scope=key[1]):
                self.assertIn(key, self.sig, f"missed: {description}")

    def test_nothing_unexpected_is_raised(self):
        self.assertEqual(self.sig - set(EXPECTED), set())

    def test_t2_is_clean(self):
        # T2 matches the protocol on criterion, sample size and result. If the
        # tool flags it, the tool is wrong -- this is the false-positive guard.
        self.assertEqual([f.id for f in self.findings if f.scope == "T2"], [])

    def test_t4_raises_only_the_documentation_point(self):
        self.assertEqual({f.rule_id for f in self.findings if f.scope == "T4"}, {"R-22"})

    # Sentences whose whole job is to state the boundary. They necessarily
    # contain verdict words ("does not determine whether the test passed or
    # failed"), so they are removed before scanning for verdict language --
    # otherwise the disclaimer trips the test that enforces the disclaimer.
    DISCLAIMERS = (
        "this tool does not determine whether the test passed or failed",
        "the disposition is the reviewer's to determine, not this tool's",
        "release is a decision for the reviewer and the design team",
    )

    def test_no_finding_states_a_verdict(self):
        # The boundary, enforced as a test: nothing this tool emits may read
        # as a pass/fail decision of its own.
        banned = ("this test fails", "the test fails", "the device fails",
                  "the test passed", "the test failed", "verdict",
                  "we conclude that the device", "rejected",
                  "non-conformance is confirmed", "does not meet its design inputs")
        for f in self.findings:
            text = " ".join([f.statement, f.basis, f.reviewer_action, f.uncertainty]).lower()
            for disclaimer in self.DISCLAIMERS:
                text = text.replace(disclaimer, " ")
            for phrase in banned:
                with self.subTest(finding=f.id, phrase=phrase):
                    self.assertNotIn(phrase, text)

    def test_the_boundary_is_actually_stated_where_it_matters(self):
        # The flip side: every finding that compares a result against a
        # criterion must hand the disposition back to the reviewer.
        for f in self.findings:
            if f.rule_id in {"R-14", "R-15"}:
                with self.subTest(f.id):
                    self.assertRegex(f.reviewer_action.lower(), r"reviewer|this tool does not")

    def test_priorities_are_within_the_allowed_set(self):
        self.assertTrue({f.priority for f in self.findings} <= {"high", "medium", "low"})

    def test_rule_outcomes_record_checks_that_found_nothing(self):
        _, outcomes = run_rules(
            ex.parse_document(self.protocol_doc), ex.parse_document(self.report_doc)
        )
        silent = {o.rule_id for o in outcomes if o.status == "no-finding"}
        # These ran, compared something, and had nothing to raise.
        self.assertEqual(silent, {"R-02", "R-03", "R-05", "R-11", "R-19"})
        for o in outcomes:
            with self.subTest(o.rule_id):
                self.assertIn(o.status, {"findings", "no-finding", "not-applicable"})

    def test_run_is_deterministic(self):
        again = review(self.protocol_doc, self.report_doc)
        self.assertEqual(
            [(f.id, f.rule_id, f.scope, f.statement) for f in again],
            [(f.id, f.rule_id, f.scope, f.statement) for f in self.findings],
        )


if __name__ == "__main__":
    unittest.main()
