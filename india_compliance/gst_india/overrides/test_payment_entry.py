import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.overrides import payment_entry


class TestPaymentEntryUtils(IntegrationTestCase):
    # ---------- get_proportionate_tax ----------

    def test_get_proportionate_tax_returns_proportional_amount(self):
        result = payment_entry.get_proportionate_tax(100, 50, 200)
        self.assertEqual(result, 25.0)

    def test_get_proportionate_tax_returns_zero_when_base_amount_is_zero(self):
        result = payment_entry.get_proportionate_tax(100, 50, 0)
        self.assertEqual(result, 0)

    def test_get_proportionate_tax_returns_zero_for_zero_allocated_amount(self):
        result = payment_entry.get_proportionate_tax(100, 0, 200)
        self.assertEqual(result, 0.0)

    # ---------- get_taxable_base_amount ----------

    def test_get_taxable_base_amount_subtracts_included_taxes(self):
        pe = frappe._dict(base_paid_amount=500, get_included_taxes=lambda: 90)
        self.assertEqual(payment_entry.get_taxable_base_amount(pe), 410.0)

    def test_get_taxable_base_amount_returns_zero_when_fully_tax(self):
        pe = frappe._dict(base_paid_amount=90, get_included_taxes=lambda: 90)
        self.assertEqual(payment_entry.get_taxable_base_amount(pe), 0.0)

    def test_get_taxable_base_amount_returns_paid_amount_when_no_included_taxes(self):
        pe = frappe._dict(base_paid_amount=500, get_included_taxes=lambda: 0)
        self.assertEqual(payment_entry.get_taxable_base_amount(pe), 500.0)

    def test_get_taxable_base_amount_handles_none_values(self):
        pe = frappe._dict(base_paid_amount=None, get_included_taxes=lambda: 0)
        self.assertEqual(payment_entry.get_taxable_base_amount(pe), 0.0)

    # ---------- get_outstanding_reference_documents ----------

    @patch("erpnext.accounts.doctype.payment_entry.payment_entry.get_outstanding_reference_documents")
    def test_get_outstanding_reference_documents_adds_reconciliation_status(
        self, mock_erpnext_func
    ):
        mock_erpnext_func.return_value = [
            frappe._dict(
                voucher_no="PI-001",
                voucher_type="Purchase Invoice",
                invoice_amount=100,
            ),
            frappe._dict(
                voucher_no="SI-001",
                voucher_type="Sales Invoice",
                invoice_amount=200,
            ),
        ]

        with patch.object(
            payment_entry,
            "get_reconciliation_status_for_invoice_list",
            return_value={"PI-001": "Partially Reconciled"},
        ):
            result = payment_entry.get_outstanding_reference_documents("{}")
            self.assertEqual(result[0]["reconciliation_status"], "Partially Reconciled")

    @patch("erpnext.accounts.doctype.payment_entry.payment_entry.get_outstanding_reference_documents")
    def test_get_outstanding_reference_documents_passes_through_without_purchase_invoices(
        self, mock_erpnext_func
    ):
        mock_erpnext_func.return_value = [
            frappe._dict(
                voucher_no="SI-001",
                voucher_type="Sales Invoice",
                invoice_amount=200,
            ),
        ]
        result = payment_entry.get_outstanding_reference_documents("{}")
        self.assertEqual(len(result), 1)
        self.assertNotIn("reconciliation_status", result[0])

    # ---------- get_reconciliation_status_for_invoice_list ----------

    def test_get_reconciliation_status_returns_none_for_empty_list(self):
        self.assertIsNone(payment_entry.get_reconciliation_status_for_invoice_list([]))

    def test_get_reconciliation_status_returns_none_for_none(self):
        self.assertIsNone(payment_entry.get_reconciliation_status_for_invoice_list(None))

    # ---------- onload ----------

    def test_onload_returns_early_when_no_references(self):
        doc = frappe._dict(references=[])
        payment_entry.onload(doc)

        self.assertIsNone(doc.get_onload().get("reconciliation_status_dict"))

    def test_onload_returns_early_when_references_is_none(self):
        doc = frappe._dict(references=None)
        payment_entry.onload(doc)

        self.assertIsNone(doc.get_onload().get("reconciliation_status_dict"))

    def test_onload_filters_only_purchase_invoice_references(self):
        doc = frappe._dict(
            references=[
                frappe._dict(
                    reference_doctype="Sales Invoice", reference_name="SI-001"
                ),
                frappe._dict(
                    reference_doctype="Journal Entry", reference_name="JE-001"
                ),
            ]
        )
        with patch.object(
            payment_entry, "get_reconciliation_status_for_invoice_list"
        ) as mock_status:
            payment_entry.onload(doc)
            mock_status.assert_called_once_with([])

    def test_onload_sets_reconciliation_status_dict(self):
        doc = frappe._dict(
            references=[
                frappe._dict(
                    reference_doctype="Purchase Invoice", reference_name="PI-001"
                ),
                frappe._dict(
                    reference_doctype="Sales Invoice", reference_name="SI-001"
                ),
            ]
        )
        with patch.object(
            payment_entry,
            "get_reconciliation_status_for_invoice_list",
            return_value={"PI-001": "Unreconciled"},
        ):
            payment_entry.onload(doc)
            self.assertEqual(
                doc.get_onload().get("reconciliation_status_dict"),
                {"PI-001": "Unreconciled"},
            )

    # ---------- validate ----------

    def test_validate_returns_early_when_no_taxes(self):
        doc = frappe._dict(taxes=[])
        payment_entry.validate(doc)

    def test_validate_sets_is_export_with_gst_for_customer(self):
        doc = frappe._dict(taxes=[frappe._dict(account_head="GST")], party_type="Customer")
        with patch.object(
            payment_entry, "validate_transaction_for_advance_payment"
        ) as mock_validate:
            payment_entry.validate(doc)
            self.assertEqual(doc.is_export_with_gst, 1)
            mock_validate.assert_called_once_with(doc, None)

    def test_validate_raises_for_supplier_with_gst_taxes(self):
        doc = frappe._dict(
            taxes=[frappe._dict(gst_tax_type="cgst", tax_amount=100)],
            party_type="Supplier",
        )
        with patch.object(payment_entry, "set_gst_tax_type"):
            self.assertRaisesRegex(
                frappe.ValidationError,
                "GST Taxes are not allowed for Supplier Advance Payment Entry",
                payment_entry.validate,
                doc,
            )

    def test_validate_skips_supplier_without_gst_taxes(self):
        doc = frappe._dict(
            taxes=[
                frappe._dict(gst_tax_type="other", tax_amount=100),
            ],
            party_type="Supplier",
        )
        with patch.object(payment_entry, "set_gst_tax_type"):
            payment_entry.validate(doc)

    # ---------- before_cancel ----------

    def test_before_cancel_returns_early_when_no_taxes(self):
        doc = frappe._dict(taxes=[])
        payment_entry.before_cancel(doc)

    def test_before_cancel_calls_validate_backdated_transaction(self):
        doc = frappe._dict(
            taxes=[frappe._dict(gst_tax_type="cgst", tax_amount=100)]
        )
        with patch.object(payment_entry, "validate_backdated_transaction") as mock_vbt:
            payment_entry.before_cancel(doc)
            mock_vbt.assert_called_once_with(doc, action="cancel")

    # ---------- validate_backdated_transaction ----------

    def test_validate_backdated_transaction_skips_when_no_gst_taxes(self):
        doc = frappe._dict(
            taxes=[frappe._dict(gst_tax_type="other", tax_amount=100)]
        )
        with patch.object(payment_entry, "_validate_backdated_transaction") as mock_inner:
            payment_entry.validate_backdated_transaction(doc)
            mock_inner.assert_not_called()

    def test_validate_backdated_transaction_calls_inner_with_gst_tax(self):
        doc = frappe._dict(taxes=[frappe._dict(gst_tax_type="cgst", tax_amount=100)])
        with patch.object(payment_entry, "_validate_backdated_transaction") as mock_inner:
            payment_entry.validate_backdated_transaction(doc)
            mock_inner.assert_called_once_with(doc, action="submit")

    def test_validate_backdated_transaction_skips_gst_taxes_with_zero_amount(self):
        doc = frappe._dict(taxes=[frappe._dict(gst_tax_type="cgst", tax_amount=0)])
        with patch.object(payment_entry, "_validate_backdated_transaction") as mock_inner:
            payment_entry.validate_backdated_transaction(doc)
            mock_inner.assert_not_called()

    def test_validate_backdated_transaction_supports_custom_action(self):
        doc = frappe._dict(taxes=[frappe._dict(gst_tax_type="igst", tax_amount=50)])
        with patch.object(payment_entry, "_validate_backdated_transaction") as mock_inner:
            payment_entry.validate_backdated_transaction(doc, action="cancel")
            mock_inner.assert_called_once_with(doc, action="cancel")

    # ---------- update_party_details ----------

    def test_update_party_details_returns_expected_structure(self):
        customer = "_Test Registered Customer"
        with patch.object(
            payment_entry, "get_default_address", return_value=None
        ), patch.object(
            payment_entry,
            "get_gst_details",
            return_value={
                "gst_category": "Registered Regular",
                "gstin": "27AAQCA8719H1Z6",
            },
        ):
            result = payment_entry.update_party_details(
                json.dumps({"customer": customer}),
                "Payment Entry",
                "_Test Indian Registered Company",
            )
            self.assertIn("customer_address", result)
            self.assertIsNone(result["customer_address"])
            self.assertEqual(result["gst_category"], "Registered Regular")
            self.assertEqual(result["gstin"], "27AAQCA8719H1Z6")

    def test_update_party_details_with_address_sets_customer_address(self):
        customer = "_Test Registered Customer"
        address = "_Test Registered Customer-Billing"
        with patch.object(
            payment_entry, "get_default_address", return_value=address
        ), patch.object(
            payment_entry,
            "get_gst_details",
            return_value={"gst_category": "Registered Regular"},
        ), patch(
            "india_compliance.gst_india.overrides.payment_entry.frappe.db.get_value",
            return_value={"billing_address_gstin": "27AAQCA8719H1Z6"},
        ):
            result = payment_entry.update_party_details(
                json.dumps({"customer": customer}),
                "Payment Entry",
                "_Test Indian Registered Company",
            )
            self.assertEqual(result["customer_address"], address)

    # ---------- get_proportionate_taxes_for_row ----------

    def test_get_proportionate_taxes_for_row_calculates_correctly(self):
        pe = frappe._dict(
            base_paid_amount=500,
            get_included_taxes=lambda: 0,
            calculate_base_allocated_amount_for_reference=lambda ref: 100,
        )
        reference_row = frappe._dict(reference_name="INV-001")
        taxes = {
            "Output Tax CGST - _TIRC": 45.0,
            "Output Tax SGST - _TIRC": 45.0,
        }
        result = payment_entry.get_proportionate_taxes_for_row(pe, reference_row, taxes)
        self.assertEqual(result["Output Tax CGST - _TIRC"], 9.0)
        self.assertEqual(result["Output Tax SGST - _TIRC"], 9.0)

    def test_get_proportionate_taxes_for_row_returns_zero_when_no_base(self):
        pe = frappe._dict(
            base_paid_amount=90,
            get_included_taxes=lambda: 90,
            calculate_base_allocated_amount_for_reference=lambda ref: 100,
        )
        reference_row = frappe._dict(reference_name="INV-001")
        taxes = {"Output Tax CGST - _TIRC": 45.0}
        result = payment_entry.get_proportionate_taxes_for_row(pe, reference_row, taxes)
        self.assertEqual(result["Output Tax CGST - _TIRC"], 0.0)

    # ---------- balance_taxes ----------

    def test_balance_taxes_subtracts_other_allocations(self):
        pe = frappe._dict(
            base_paid_amount=500,
            get_included_taxes=lambda: 0,
            references=[
                frappe._dict(reference_name="INV-001"),
                frappe._dict(reference_name="INV-002"),
            ],
            calculate_base_allocated_amount_for_reference=lambda ref: 100,
        )
        reference_row = frappe._dict(reference_name="INV-001")
        taxes = {"Output Tax CGST - _TIRC": 45.0}
        result = payment_entry.balance_taxes(pe, reference_row, taxes)
        self.assertEqual(result["Output Tax CGST - _TIRC"], 36.0)

    def test_balance_taxes_does_not_subtract_own_reference(self):
        pe = frappe._dict(
            base_paid_amount=500,
            get_included_taxes=lambda: 0,
            references=[
                frappe._dict(reference_name="INV-001"),
            ],
            calculate_base_allocated_amount_for_reference=lambda ref: 100,
        )
        reference_row = frappe._dict(reference_name="INV-001")
        taxes = {"Output Tax CGST - _TIRC": 45.0}
        result = payment_entry.balance_taxes(pe, reference_row, taxes)
        self.assertEqual(result["Output Tax CGST - _TIRC"], 45.0)

    # ---------- get_advance_payment_entries_for_regional ----------

    def test_get_advance_payment_entries_returns_early_without_condition(self):
        with patch.object(
            payment_entry,
            "get_advance_payment_entries",
            return_value=[frappe._dict(reference_name="PE-001")],
        ):
            result = payment_entry.get_advance_payment_entries_for_regional(
                party_type="Customer",
                party="_Test Customer",
                party_account="Debtors - _TIRC",
                order_doctype="Sales Order",
            )
            self.assertEqual(len(result), 1)

    def test_get_advance_payment_entries_returns_early_without_payment_entries(self):
        with patch.object(payment_entry, "get_advance_payment_entries", return_value=[]):
            result = payment_entry.get_advance_payment_entries_for_regional(
                party_type="Customer",
                party="_Test Customer",
                party_account="Debtors - _TIRC",
                order_doctype="Sales Order",
                condition=frappe._dict({"company": "_Test Indian Registered Company"}),
            )
            self.assertEqual(result, [])

    # ---------- get_included_taxes_query ----------

    def test_get_included_taxes_query_returns_query_object(self):
        result = payment_entry.get_included_taxes_query(
            ["Output Tax CGST - _TIRC", "Output Tax SGST - _TIRC"]
        )
        sql = str(result).lower()
        self.assertIn("advance taxes and charges", sql)
        self.assertIn("included_in_paid_amount", sql)

    def test_get_included_taxes_query_accepts_payment_entries_filter(self):
        result = payment_entry.get_included_taxes_query(
            ["Output Tax CGST - _TIRC"], payment_entries=["PE-001"]
        )
        sql = str(result).lower()
        self.assertIn("'pe-001'", sql)

    def test_get_included_taxes_query_filters_by_gst_accounts(self):
        result = payment_entry.get_included_taxes_query(["Output Tax CGST - _TIRC"])
        sql = str(result).lower()
        self.assertIn("output tax cgst", sql)

    # ---------- adjust_allocations_for_taxes_in_payment_reconciliation ----------

    def test_adjust_allocations_returns_early_without_allocation(self):
        doc = frappe._dict(allocation=[])
        payment_entry.adjust_allocations_for_taxes_in_payment_reconciliation(doc)

    def test_adjust_allocations_returns_early_when_no_taxes_found(self):
        doc = frappe._dict(
            allocation=[frappe._dict(reference_name="PE-001")], company="_Test"
        )
        with patch.object(payment_entry, "get_taxes_summary", return_value={}):
            payment_entry.adjust_allocations_for_taxes_in_payment_reconciliation(doc)
            self.assertIsNone(doc.allocation[0].get("amount"))
