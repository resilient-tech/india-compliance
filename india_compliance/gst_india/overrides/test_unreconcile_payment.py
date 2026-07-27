from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.overrides import unreconcile_payment


class TestUnreconcilePayment(IntegrationTestCase):
    # ---------- before_submit ----------

    def test_before_submit_skips_non_payment_entry(self):
        doc = frappe._dict(voucher_type="Sales Invoice", allocations=[])
        unreconcile_payment.before_submit(doc)

    def test_before_submit_returns_early_with_no_allocations(self):
        doc = frappe._dict(
            voucher_type="Payment Entry", voucher_no="PE-001", allocations=[]
        )
        unreconcile_payment.before_submit(doc)

    def test_before_submit_returns_early_without_allocations_key(self):
        doc = frappe._dict(voucher_type="Payment Entry", voucher_no="PE-001")
        unreconcile_payment.before_submit(doc)

    @patch(
        "india_compliance.gst_india.overrides.unreconcile_payment.frappe.get_all",
        return_value=[],
    )
    def test_before_submit_skips_when_no_voucher_detail_nos(self, mock_get_all):
        doc = frappe._dict(
            voucher_type="Payment Entry",
            voucher_no="PE-001",
            allocations=[
                frappe._dict(
                    reference_doctype="Sales Invoice", reference_name="INV-001"
                )
            ],
        )
        with patch.object(
            unreconcile_payment, "reverse_gst_adjusted_against_payment_entry"
        ) as mock_reverse:
            unreconcile_payment.before_submit(doc)
            mock_reverse.assert_not_called()

    @patch(
        "india_compliance.gst_india.overrides.unreconcile_payment.frappe.get_all",
        return_value=["PE-REF-001"],
    )
    def test_before_submit_calls_reverse_gst_for_each_voucher_detail_no(
        self, mock_get_all
    ):
        doc = frappe._dict(
            voucher_type="Payment Entry",
            voucher_no="PE-001",
            allocations=[
                frappe._dict(
                    reference_doctype="Sales Invoice", reference_name="INV-001"
                )
            ],
        )
        with patch.object(
            unreconcile_payment, "reverse_gst_adjusted_against_payment_entry"
        ) as mock_reverse:
            unreconcile_payment.before_submit(doc)
            mock_reverse.assert_called_once_with("PE-REF-001", "PE-001")

    @patch(
        "india_compliance.gst_india.overrides.unreconcile_payment.frappe.get_all",
        return_value=["PRE-REF-001", "PRE-REF-002"],
    )
    def test_before_submit_calls_reverse_gst_for_multiple_voucher_detail_nos(
        self, mock_get_all
    ):
        doc = frappe._dict(
            voucher_type="Payment Entry",
            voucher_no="PE-001",
            allocations=[
                frappe._dict(
                    reference_doctype="Sales Invoice", reference_name="INV-001"
                )
            ],
        )
        with patch.object(
            unreconcile_payment, "reverse_gst_adjusted_against_payment_entry"
        ) as mock_reverse:
            unreconcile_payment.before_submit(doc)
            self.assertEqual(mock_reverse.call_count, 2)

    @patch(
        "india_compliance.gst_india.overrides.unreconcile_payment.frappe.get_all",
        return_value=["PRE-REF-001"],
    )
    def test_before_submit_queries_with_correct_filters(self, mock_get_all):
        doc = frappe._dict(
            voucher_type="Payment Entry",
            voucher_no="PE-001",
            allocations=[
                frappe._dict(
                    reference_doctype="Sales Invoice", reference_name="INV-001"
                )
            ],
        )
        unreconcile_payment.before_submit(doc)
        mock_get_all.assert_called_once_with(
            "Payment Entry Reference",
            {
                "parent": "PE-001",
                "reference_doctype": "Sales Invoice",
                "reference_name": "INV-001",
                "docstatus": 1,
            },
            pluck="name",
        )

    # ---------- reverse_gst_adjusted_against_payment_entry ----------

    @patch(
        "india_compliance.gst_india.overrides.unreconcile_payment.frappe.get_all",
        return_value=[],
    )
    def test_reverse_gst_returns_early_with_no_gl_entries(self, mock_get_all):
        unreconcile_payment.reverse_gst_adjusted_against_payment_entry(
            "VD-001", "PE-001"
        )

    def test_reverse_gst_cancels_and_reverses_gl_entries(self):
        gl_entry = frappe._dict(
            name="GL-001", account="Output Tax CGST - _TIRC", debit=45.0
        )
        with patch(
            "india_compliance.gst_india.overrides.unreconcile_payment.frappe.get_all",
            return_value=[gl_entry],
        ), patch(
            "india_compliance.gst_india.overrides.unreconcile_payment.frappe.db.set_value"
        ) as mock_set_value, patch(
            "india_compliance.gst_india.overrides.unreconcile_payment.make_reverse_gl_entries"
        ) as mock_reverse_gl:
            unreconcile_payment.reverse_gst_adjusted_against_payment_entry(
                "VD-001", "PE-001"
            )
            expected_filters = {
                "voucher_type": "Payment Entry",
                "voucher_no": "PE-001",
                "voucher_detail_no": "VD-001",
            }
            mock_set_value.assert_called_once_with(
                "GL Entry", expected_filters, "is_cancelled", 1
            )
            mock_reverse_gl.assert_called_once_with([gl_entry], partial_cancel=True)
