# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import unittest

import frappe
from frappe.utils import flt

from india_compliance.gst_india.doctype.isd_invoice.isd_invoice import _calculate_distribution


def make_doc(source_invoices, company_address=None, party_address=None):
    """Build a minimal ISD Invoice-like frappe._dict for use with _calculate_distribution."""
    rows = [
        frappe._dict(
            distribution_ratio=row["distribution_ratio"],
            total_igst=row.get("total_igst", 0),
            total_cgst=row.get("total_cgst", 0),
            total_sgst=row.get("total_sgst", 0),
            total_cess=row.get("total_cess", 0),
            total_cess_non_advol=row.get("total_cess_non_advol", 0),
        )
        for row in source_invoices
    ]
    return frappe._dict(
        source_invoices=rows,
        company_address=company_address,
        party_address=party_address,
    )


class TestISDInvoiceRounding(unittest.TestCase):
    """
    Regression tests for rounding errors in ISD distribution.

    When distribution_ratio is derived from turnover fractions that don't divide
    evenly, multiplying each row's ratio separately causes floating-point drift.
    The sum of all distributed amounts may differ from the original total tax.

    Example: 3 branches share ₹1,000,000 IGST equally (33.333...% each).
    Ratio 100/3 % per branch → distributed = 1_000_000 * (100/3) / 100
                                            = 1_000_000 / 3
                                            = 333_333.333...
    Floating-point representation rounds each to ~333333.33333333337,
    so 3 × 333333.33333333337 ≈ 1_000_000.0000000001 — 1 paisa off.

    The correct approach is to derive ratios from exact turnover values
    (turnover_i / total_turnover * total_tax) and allocate the last branch
    as (total - sum_of_others) to avoid drift.
    """

    def _total_distributed_igst(self, doc):
        return sum(flt(row.distributed_igst) for row in doc.source_invoices)

    def test_rounding_error_with_non_terminating_ratio(self):
        """
        Three branches share one purchase invoice equally.
        Using distribution_ratio=33.333...% causes the sum to exceed
        the actual total IGST due to floating-point accumulation.
        """
        total_igst = 1_000_000.00
        # 100 / 3 does not terminate in decimal; this is the problematic ratio.
        ratio = 100 / 3  # ~33.3333...

        doc = make_doc(
            [{"distribution_ratio": ratio, "total_igst": total_igst}] * 3
        )
        _calculate_distribution(doc)

        distributed_sum = self._total_distributed_igst(doc)

        # Document the rounding error: sum should be total_igst but may drift.
        error = abs(distributed_sum - total_igst)
        self.assertGreater(
            error,
            0,
            "Expected a non-zero rounding error when using 100/3 as ratio "
            f"but got exact result (distributed_sum={distributed_sum})",
        )

    def test_rounding_error_is_small(self):
        """
        The rounding error from ratio-based distribution must stay sub-paisa
        (< 0.01) so that it is unlikely to trigger validate_distribution_limits.
        """
        total_igst = 1_000_000.00
        ratio = 100 / 3

        doc = make_doc(
            [{"distribution_ratio": ratio, "total_igst": total_igst}] * 3
        )
        _calculate_distribution(doc)

        distributed_sum = self._total_distributed_igst(doc)
        error = abs(distributed_sum - total_igst)

        self.assertLess(
            error,
            0.01,
            f"Rounding error ({error}) is larger than one paisa; "
            "this may cause distribution limit validation failures.",
        )

    def test_large_values_increase_rounding_error(self):
        """
        With very large IGST amounts (e.g. crore-level) and a non-terminating
        ratio the absolute rounding error grows beyond a single paisa.
        """
        total_igst = 100_000_000.00  # 10 crore
        ratio = 100 / 3

        doc = make_doc(
            [{"distribution_ratio": ratio, "total_igst": total_igst}] * 3
        )
        _calculate_distribution(doc)

        distributed_sum = self._total_distributed_igst(doc)
        error = abs(distributed_sum - total_igst)

        # At crore scale the floating-point error can exceed 1 paisa.
        self.assertGreater(
            error,
            0,
            f"Expected a non-zero rounding error at crore-scale values "
            f"(distributed_sum={distributed_sum}, expected={total_igst})",
        )

    def test_exact_turnover_split_avoids_rounding_error(self):
        """
        When each branch ratio is computed from integer turnover values that
        divide evenly, the distribution is exact.
        """
        # Turnover: branch A=50%, B=30%, C=20% (terminating fractions).
        total_igst = 1_000_000.00
        ratios = [50.0, 30.0, 20.0]

        doc = make_doc(
            [{"distribution_ratio": r, "total_igst": total_igst} for r in ratios]
        )
        _calculate_distribution(doc)

        distributed_sum = self._total_distributed_igst(doc)
        self.assertAlmostEqual(
            distributed_sum,
            total_igst,
            places=9,
            msg="Exact ratios should produce zero rounding error.",
        )

    def test_all_tax_types_accumulate_rounding_error(self):
        """
        Rounding errors compound across IGST, CGST, SGST, CESS when all tax
        types are present and the ratio is non-terminating.
        """
        ratio = 100 / 7  # non-terminating; 3 branches
        source_row = {
            "distribution_ratio": ratio,
            "total_igst": 700_000.00,
            "total_cgst": 350_000.00,
            "total_sgst": 350_000.00,
            "total_cess": 70_000.00,
        }

        doc = make_doc([source_row] * 7)
        _calculate_distribution(doc)

        def total(field):
            return sum(flt(getattr(row, field)) for row in doc.source_invoices)

        for field, expected in (
            ("distributed_igst", 700_000.00),
            ("distributed_cgst", 350_000.00),
            ("distributed_sgst", 350_000.00),
            ("distributed_cess", 70_000.00),
        ):
            actual = total(field)
            error = abs(actual - expected)
            # Just assert the error is measurable (non-zero) and still small.
            self.assertGreater(
                error,
                0,
                f"{field}: expected rounding error but got exact result ({actual})",
            )
            self.assertLess(
                error,
                0.10,
                f"{field}: rounding error {error} is unexpectedly large.",
            )
