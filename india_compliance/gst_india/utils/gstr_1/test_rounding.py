# Copyright (c) 2024, Resilient Tech and Contributors
# See license.txt

"""Tests for settling GSTR-1 amounts once, in the data layer.

Amounts used to be rounded separately by each section: the document sections rounded per invoice
per rate, HSN rounded per HSN code across invoices, and the two totals then had to be forced to
agree afterwards. Now the data layer settles each amount once and every section only adds up what
it is given, so the totals agree whichever way the rows are grouped.

Needs a site (rounding reads site settings) but no test records:
    bench --site <site> run-tests --module india_compliance.gst_india.utils.gstr_1.test_rounding
"""

import math
import unittest
from typing import ClassVar

import frappe
from frappe.utils import cint, flt

from india_compliance.gst_india.utils.gstr_1 import Category, SubCategory
from india_compliance.gst_india.utils.gstr_1 import DocField as doc
from india_compliance.gst_india.utils.gstr_1.gstr_1_books_map import (
    BooksDataMapper,
    GSTR1BooksData,
)
from india_compliance.gst_india.utils.gstr_1.gstr_1_data import GSTR1Invoices
from india_compliance.gst_india.utils.gstr_1.sections._shared import sum_column

AMOUNTS = ("taxable_value", "igst_amount", "cgst_amount", "sgst_amount", "total_cess_amount")


def row(invoice_no, rate, hsn, **amounts):
    """One item row as the query returns it."""
    return frappe._dict(
        {
            "invoice_no": invoice_no,
            "gst_rate": rate,
            "gst_hsn_code": hsn,
            "uom": "NOS-NUMBERS",
            "gst_treatment": "Taxable",
            **dict.fromkeys(AMOUNTS, 0),
            **amounts,
        }
    )


def settle(rows):
    lost = GSTR1Invoices({}).settle_amounts(rows)
    return rows, lost


class TestSettleAmounts(unittest.TestCase):
    def test_rows_add_back_to_the_rate_total(self):
        # three thirds of a rupee: rounding each on its own would give 1.00, not 0.99
        rows, _ = settle([row("A", 18, "1001", taxable_value=0.333) for _ in range(3)])
        self.assertEqual(flt(sum(r.taxable_value for r in rows), 2), flt(0.333 * 3, 2))

    def test_the_same_rows_add_up_the_same_grouped_any_other_way(self):
        """This is the property the HSN reconciliation used to fake.

        The document sections group by invoice and rate; HSN groups by HSN code across invoices.
        Both are sums of the same settled rows, so both land on the same grand total.
        """
        rows, _ = settle(
            [
                row("A", 18, "1001", cgst_amount=8395.11),
                row("A", 18, "2002", cgst_amount=5347.355),
                row("B", 18, "1001", cgst_amount=2313.095),
                row("B", 5, "1001", cgst_amount=144.826),
            ]
        )

        by_invoice_and_rate = sum(
            flt(sum(r.cgst_amount for r in rows if (r.invoice_no, r.gst_rate) == key), 2)
            for key in {(r.invoice_no, r.gst_rate) for r in rows}
        )
        by_hsn = sum(
            flt(sum(r.cgst_amount for r in rows if r.gst_hsn_code == hsn), 2)
            for hsn in {r.gst_hsn_code for r in rows}
        )

        self.assertEqual(flt(by_invoice_and_rate, 2), flt(by_hsn, 2))

    def test_each_nil_bucket_settles_on_its_own(self):
        """Nil-rated, exempted and non-GST are filed apart, and all three sit at rate zero.

        Settled as one pool, a leftover paisa moves between buckets and each stops matching
        what its own lines add up to.
        """
        rows, _ = settle(
            [
                row("A", 0, "1001", taxable_value=100.005, gst_treatment="Nil-Rated"),
                row("A", 0, "1001", taxable_value=33.335, gst_treatment="Exempted"),
                row("A", 0, "1001", taxable_value=23.335, gst_treatment="Non-GST"),
            ]
        )

        for settled, raw in zip(rows, (100.005, 33.335, 23.335), strict=True):
            self.assertEqual(settled.taxable_value, flt(raw, 2))

    def test_each_rate_of_an_invoice_settles_on_its_own(self):
        rows, _ = settle(
            [
                row("A", 18, "1001", cgst_amount=10.005),
                row("A", 5, "1001", cgst_amount=10.005),
            ]
        )
        for settled in rows:
            self.assertEqual(settled.cgst_amount, flt(10.005, 2))

    def test_no_row_carries_everyone_elses_rounding(self):
        # the replaced reconciliation dumped the whole difference on one row
        rows, _ = settle([row("A", 18, "1001", cgst_amount=0.005) for _ in range(100)])
        for settled in rows:
            self.assertLessEqual(abs(settled.cgst_amount), 0.01)

    def test_credit_notes_settle_while_staying_negative(self):
        rows, _ = settle([row("A", 18, "1001", cgst_amount=-5225.285) for _ in range(2)])
        self.assertEqual(flt(sum(r.cgst_amount for r in rows), 2), flt(-5225.285 * 2, 2))
        self.assertTrue(all(r.cgst_amount < 0 for r in rows))

    def test_a_settled_amount_is_left_alone_the_second_time(self):
        rows, _ = settle([row("A", 18, "1001", cgst_amount=100.004)])
        once = rows[0].cgst_amount
        settle(rows)
        self.assertEqual(rows[0].cgst_amount, once)

    def test_reports_what_rounding_cost(self):
        _, lost = settle([row("A", 18, "1001", cgst_amount=10.005)])
        self.assertAlmostEqual(lost["cgst_amount"], 10.005 - flt(10.005, 2), places=6)

    def test_nothing_lost_when_the_amounts_already_have_two_decimals(self):
        _, lost = settle([row("A", 18, "1001", cgst_amount=10.00, taxable_value=55.55)])
        self.assertEqual({value for value in lost.values() if value}, set())

    def test_tax_survives_on_a_row_whose_taxable_value_rounds_away(self):
        """Each amount settles on its own, so a row can keep tax after its taxable value goes.

        The sections used to skip such a row on taxable value alone, which dropped its tax
        out of the return while HSN -- built before the skip -- still counted it.
        """
        rows, _ = settle(
            [
                row(
                    "A",
                    18,
                    "1001",
                    taxable_value=0.005,
                    cgst_amount=0.00045,  # 9% of it -- the two settle onto different rows
                    invoice_category=Category.B2B.value,
                    invoice_sub_category=SubCategory.B2B_REGULAR.value,
                )
                for _ in range(100)
            ]
        )
        stranded = [r for r in rows if not r.taxable_value and r.cgst_amount]

        mapper = GSTR1BooksData(frappe._dict())
        _hsn, by_invoice, *_ = mapper.get_structured_data(rows)
        kept = [r for group in by_invoice.values() for items in group.values() for r in items]

        self.assertTrue(stranded, "expected the split to leave tax on a zero-taxable row")
        self.assertEqual(flt(sum(r.cgst_amount for r in kept), 2), flt(sum(r.cgst_amount for r in rows), 2))


class TestTotalsStayExact(unittest.TestCase):
    """Adding up must not walk back the accuracy settling bought."""

    AMOUNTS: ClassVar[tuple] = (600100.005, 600033.335, 600000.005)

    def rows(self):
        return [row("A", 18, "1001", taxable_value=amount) for amount in self.AMOUNTS]

    def test_totalling_rows_is_exact(self):
        self.assertEqual(sum_column(self.rows(), "taxable_value"), flt(math.fsum(self.AMOUNTS), 2))

    def test_settling_rows_is_exact(self):
        settled, _ = settle(self.rows())
        total = flt(sum(settled_row.taxable_value for settled_row in settled), 2)

        self.assertEqual(total, flt(math.fsum(self.AMOUNTS), 2))


class TestNoReconciliationLeft(unittest.TestCase):
    def test_the_hsn_adjustment_is_gone(self):
        # it existed only to force HSN totals onto the document totals
        self.assertFalse(hasattr(BooksDataMapper, "adjust_hsn_totals"))

    def test_the_cross_section_accumulator_is_gone(self):
        # HSN used to read totals the other sections had written, so it had to run last
        self.assertFalse(hasattr(BooksDataMapper, "initialize_totals"))


class TestRoundingDifferenceReport(unittest.TestCase):
    """The page offers to post a journal entry from these figures, so the names matter."""

    JOURNALLED: ClassVar[set] = {
        doc.IGST,
        doc.CGST,
        doc.SGST,
        doc.CESS,
    }

    def report(self, lost):
        prepared = {}
        BooksDataMapper().update_rounding_difference(prepared, lost)
        return prepared["rounding_difference"]["rounding_difference"]

    def test_reported_under_the_invoice_total_names(self):
        reported = self.report(dict.fromkeys(AMOUNTS, 0.0))
        self.assertTrue(self.JOURNALLED <= set(reported), f"missing: {self.JOURNALLED - set(reported)}")
        self.assertIn(doc.TAXABLE_VALUE, reported)

    def test_no_query_column_names_leak_through(self):
        # "cgst_amount" is what the query calls it; the journal entry looks for "total_cgst_amount"
        self.assertEqual(set(self.report(dict.fromkeys(AMOUNTS, 0.0))) & set(AMOUNTS), {"total_cess_amount"})

    def test_every_amount_is_reported_even_when_it_did_not_move(self):
        self.assertEqual(len(self.report(dict.fromkeys(AMOUNTS, 0.0))), len(AMOUNTS))

    def test_the_residual_is_carried_through(self):
        precision = cint(frappe.db.get_default("currency_precision")) or 2
        reported = self.report({**dict.fromkeys(AMOUNTS, 0.0), "cgst_amount": 0.006})[doc.CGST]

        self.assertEqual(reported, flt(0.006, precision))
        self.assertTrue(reported)

    def test_float_dust_is_not_a_residual(self):
        """Adding thousands of amounts leaves dust well below a paisa."""
        reported = self.report({**dict.fromkeys(AMOUNTS, 0.0), "cgst_amount": 1.09e-11})

        self.assertFalse(any(reported.values()), reported)


class TestHsnRowsAddUp(unittest.TestCase):
    def test_document_value_equals_the_sum_of_its_own_parts(self):
        """The portal checks this, and the replaced reconciliation broke it.

        It adjusted the tax amounts after `document_value` had already been worked out, leaving the
        row claiming a total its own columns no longer added up to.
        """
        mapper = BooksDataMapper()
        prepared = {}
        mapper.process_data_for_hsn_summary(
            {
                "HSN Summary": {
                    "1001 - NOS-NUMBERS - 18.0": [
                        row("A", 18, "1001", taxable_value=100.0, cgst_amount=9.0, sgst_amount=9.0),
                        row("B", 18, "1001", taxable_value=50.0, cgst_amount=4.5, sgst_amount=4.5),
                    ]
                }
            },
            prepared,
        )

        for hsn_row in prepared["HSN Summary"].values():
            parts = sum(
                hsn_row.get(field, 0) for field in (doc.TAXABLE_VALUE, doc.IGST, doc.CGST, doc.SGST, doc.CESS)
            )
            self.assertEqual(hsn_row[doc.DOC_VALUE], flt(parts, 2))


if __name__ == "__main__":
    unittest.main()
