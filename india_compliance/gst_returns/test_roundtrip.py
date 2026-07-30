# Copyright (c) 2024, Resilient Tech and Contributors
# See license.txt

"""Self-tests for the losslessness harness. Site-less."""

import unittest

from .roundtrip import assert_roundtrip


class TestAssertRoundtrip(unittest.TestCase):
    def test_identical_passes(self):
        data = {"b2b": [{"ctin": "24AAQCA8719H1ZC", "txval": 100.0}]}
        assert_roundtrip(data, data)

    def test_empty_vs_absent_passes(self):
        # empty drops out
        assert_roundtrip({"a": 1, "b": "", "c": None}, {"a": 1})
        assert_roundtrip({"a": 1}, {"a": 1, "b": "", "c": None})

    def test_zero_is_not_empty(self):
        # 0 not empty
        assert_roundtrip({"txval": 0}, {"txval": 0.0})
        with self.assertRaises(AssertionError):
            assert_roundtrip({"txval": 0}, {})

    def test_false_is_not_empty(self):
        with self.assertRaises(AssertionError):
            assert_roundtrip({"flag": False}, {})

    def test_empty_container_drops(self):
        # {} and [] vanish through format_data
        assert_roundtrip({"a": 1, "b": {}, "c": []}, {"a": 1})

    def test_float_precision_tolerance(self):
        assert_roundtrip({"txval": 10.501}, {"txval": 10.5})
        with self.assertRaises(AssertionError):
            assert_roundtrip({"txval": 10.5}, {"txval": 10.6})

    def test_int_float_equal(self):
        assert_roundtrip({"n": 5}, {"n": 5.0})

    def test_nested_mismatch_reports_path(self):
        a = {"b2b": [{"items": [{"txval": 10.0}]}]}
        b = {"b2b": [{"items": [{"txval": 11.0}]}]}
        with self.assertRaises(AssertionError) as cm:
            assert_roundtrip(a, b)
        self.assertIn("b2b", str(cm.exception))
        self.assertIn("txval", str(cm.exception))

    def test_list_length_mismatch_fails(self):
        with self.assertRaises(AssertionError):
            assert_roundtrip({"rows": [1, 2]}, {"rows": [1, 2, 3]})

    def test_extra_key_fails(self):
        with self.assertRaises(AssertionError):
            assert_roundtrip({"a": 1}, {"a": 1, "b": 2})


if __name__ == "__main__":
    unittest.main()
