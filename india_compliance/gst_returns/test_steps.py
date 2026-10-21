# Copyright (c) 2026, Resilient Tech and Contributors
# See license.txt

"""Pins the rules the two read styles differ on. Site-less."""

import unittest
from typing import ClassVar

from .steps import add_item_totals, decode, pick, remap, set_item_totals, take


class TestReadStyles(unittest.TestCase):
    KEYS: ClassVar[dict] = {"inum": "bill_no", "val": "document_value"}

    def test_pick_drops_what_the_portal_did_not_send(self):
        self.assertEqual(pick({"inum": "INV-1"}, self.KEYS), {"bill_no": "INV-1"})

    def test_take_lands_every_field_absent_as_none(self):
        # a re-download must clear a stale stored value, so the key has to exist
        self.assertEqual(
            take({"inum": "INV-1"}, self.KEYS),
            {"bill_no": "INV-1", "document_value": None},
        )

    def test_take_keeps_table_order(self):
        self.assertEqual(
            list(take({"val": 5, "inum": "INV-1"}, self.KEYS)),
            ["bill_no", "document_value"],
        )

    def test_remap_keeps_an_unknown_code(self):
        self.assertEqual(remap({"type": "X"}, "type", {"C": "Credit Note"}), {"type": "X"})

    def test_decode_reads_an_unknown_code_as_none(self):
        self.assertEqual(decode({"type": "X"}, "type", {"C": "Credit Note"}), {"type": None})

    def test_decode_maps_a_missing_value_through_the_none_key(self):
        # the portal reports no rate difference as no key at all, and that means 1
        self.assertEqual(decode({}, "diffprcnt", {1: 1, 0.65: 0.65, None: 1}), {"diffprcnt": 1})


class TestItemTotals(unittest.TestCase):
    ITEMS: ClassVar[list] = [
        {"taxable_value": 100, "igst": 18},
        {"taxable_value": 50, "igst": None},
    ]

    def test_set_item_totals_replaces_what_the_row_had(self):
        row = {"taxable_value": 999}
        set_item_totals(row, self.ITEMS, ("taxable_value", "igst"))
        self.assertEqual(row, {"taxable_value": 150, "igst": 18})

    def test_set_item_totals_with_no_amounts_writes_zero(self):
        row = {}
        set_item_totals(row, [{"igst": None}], ("igst",))
        self.assertEqual(row, {"igst": 0})

    def test_add_item_totals_accumulates_instead(self):
        row = {"total_taxable": 10}
        add_item_totals(row, [{"taxable_value": 5}], {"taxable_value": "total_taxable"})
        self.assertEqual(row, {"total_taxable": 15})


if __name__ == "__main__":
    unittest.main()
