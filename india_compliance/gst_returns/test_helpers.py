# Copyright (c) 2024, Resilient Tech and Contributors
# See license.txt

"""Pure self-tests for helpers. Site-less. round2 expectations = frappe.flt(x, 2)."""

import unittest
from datetime import date

from .helpers import format_date, parse_date, round2


class TestRound2(unittest.TestCase):
    def test_none_and_zero(self):
        self.assertEqual(round2(None), 0.0)
        self.assertEqual(round2(0), 0.0)
        self.assertEqual(round2(0.0), 0.0)

    def test_epsilon_corrected_halves(self):
        self.assertEqual(round2(2.675), 2.68)
        self.assertEqual(round2(-50.005), -50.0)
        self.assertEqual(round2(10.005), 10.01)
        self.assertEqual(round2(99.995), 100.0)
        self.assertEqual(round2(1234.565), 1234.57)

    def test_plain_values(self):
        self.assertEqual(round2(100), 100.0)
        self.assertEqual(round2(33.333333), 33.33)
        self.assertEqual(round2(0.1 + 0.2), 0.3)


class TestDateHelpers(unittest.TestCase):
    def test_parse_iso_and_custom_fmt(self):
        self.assertEqual(parse_date("2024-03-15"), date(2024, 3, 15))
        self.assertEqual(parse_date("15-03-2024", "%d-%m-%Y"), date(2024, 3, 15))

    def test_parse_empty(self):
        self.assertIsNone(parse_date(None))
        self.assertIsNone(parse_date(""))

    def test_parse_passthrough_date(self):
        self.assertEqual(parse_date(date(2024, 3, 15)), date(2024, 3, 15))

    def test_format_iso_and_custom_fmt(self):
        self.assertEqual(format_date(date(2024, 3, 15)), "2024-03-15")
        self.assertEqual(format_date(date(2024, 3, 15), "%d-%m-%Y"), "15-03-2024")
        self.assertIsNone(format_date(None))

    def test_roundtrip(self):
        self.assertEqual(parse_date(format_date(date(2024, 3, 15))), date(2024, 3, 15))


if __name__ == "__main__":
    unittest.main()
