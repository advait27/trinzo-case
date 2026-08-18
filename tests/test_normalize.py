"""Unit tests for criterion and result parsing -- the layer most likely to be
extended when new documents arrive."""

from __future__ import annotations

import unittest
from datetime import date

from protocolqc.normalize import (
    Qualitative,
    Range,
    Threshold,
    parse_criterion,
    parse_date,
    parse_int,
    parse_measurements,
    quantified_qualifiers,
    temperatures,
    worst_case,
)


class TestCriteria(unittest.TestCase):
    def test_greater_or_equal(self):
        c = parse_criterion("≥ 5.0 N")
        self.assertIsInstance(c, Threshold)
        self.assertEqual((c.op, c.value), (">=", 5.0))
        self.assertTrue(c.outside(4.7))
        self.assertFalse(c.outside(5.0))

    def test_less_or_equal_with_a_compound_unit(self):
        c = parse_criterion("≤ 20 particles ≥10 µm per unit")
        self.assertIsInstance(c, Threshold)
        self.assertEqual((c.op, c.value), ("<=", 20.0))
        self.assertTrue(c.outside(32))
        self.assertFalse(c.outside(12))

    def test_range(self):
        c = parse_criterion("0.20 – 0.40 N")
        self.assertIsInstance(c, Range)
        self.assertEqual((c.low, c.high), (0.20, 0.40))
        self.assertTrue(c.outside(0.45))
        self.assertTrue(c.outside(0.19))
        self.assertFalse(c.outside(0.22))

    def test_prefixed_threshold(self):
        c = parse_criterion("Reactivity grade ≤ 2")
        self.assertIsInstance(c, Threshold)
        self.assertEqual((c.op, c.value), ("<=", 2.0))

    def test_qualitative(self):
        self.assertIsInstance(parse_criterion("No visible corrosion at 24 h"), Qualitative)

    def test_empty(self):
        self.assertIsNone(parse_criterion("   "))


class TestMeasurements(unittest.TestCase):
    def test_min_and_mean(self):
        m = parse_measurements("Min 4.7 N, mean 6.1 N. Tested at ambient. Pass.")
        self.assertEqual({(x.label, x.value) for x in m}, {("min", 4.7), ("mean", 6.1)})

    def test_range_and_callout_are_not_double_counted(self):
        m = parse_measurements("Range 0.22 – 0.45 N (one unit at 0.45 N), mean 0.31 N. Pass.")
        self.assertEqual(sorted(x.value for x in m), [0.22, 0.31, 0.45])

    def test_max(self):
        m = parse_measurements("Max 12 particles. Pass.")
        self.assertEqual([(x.label, x.value) for x in m], [("max", 12.0)])

    def test_qualitative_result_yields_nothing(self):
        self.assertEqual(parse_measurements("No corrosion observed. Pass."), [])

    def test_value_labelled_by_the_criterion_itself(self):
        # "Reactivity grade 1" says neither min nor max; the only thing that
        # identifies the number is the criterion's own wording.
        crit = parse_criterion("Reactivity grade ≤ 2")
        self.assertEqual(parse_measurements("Reactivity grade 1. Pass."), [])
        found = parse_measurements("Reactivity grade 1. Pass.", crit.prefix)
        self.assertEqual([(x.label, x.value) for x in found], [("observation", 1.0)])
        self.assertFalse(crit.outside(found[0].value))
        self.assertTrue(crit.outside(3.0))

    def test_criterion_labelled_value_is_compared(self):
        crit = parse_criterion("Reactivity grade ≤ 2")
        values = parse_measurements("Reactivity grade 3 observed.", crit.prefix)
        self.assertTrue(any(crit.outside(v.value) for v in worst_case(crit, values)))

    def test_mean_is_excluded_from_the_conformity_comparison(self):
        # A mean above the criterion cannot demonstrate that every unit was.
        crit = parse_criterion("≥ 5.0 N")
        values = parse_measurements("Min 4.7 N, mean 6.1 N.")
        relevant = worst_case(crit, values)
        self.assertEqual([v.label for v in relevant], ["min"])
        self.assertTrue(any(crit.outside(v.value) for v in relevant))


class TestScalars(unittest.TestCase):
    def test_parse_int(self):
        self.assertEqual(parse_int(" 30 "), 30)
        self.assertIsNone(parse_int("Per ISO 10993-5"))

    def test_parse_date(self):
        self.assertEqual(parse_date("Date: 3 July 2026"), date(2026, 7, 3))
        self.assertEqual(parse_date("calibration due 30 June 2025"), date(2025, 6, 30))
        self.assertIsNone(parse_date("no date here"))

    def test_temperatures(self):
        self.assertEqual(temperatures("Tensile pull to failure in 37°C saline bath"), [37.0])
        self.assertEqual(temperatures("3-point bend, 37°C saline"), [37.0])
        self.assertEqual(temperatures("Immersion + potentiodynamic scan"), [])

    def test_quantified_qualifiers(self):
        self.assertEqual(quantified_qualifiers("No visible corrosion at 24 h"), ["24 h"])
        self.assertEqual(quantified_qualifiers("≥ 5.0 N"), [])


if __name__ == "__main__":
    unittest.main()
