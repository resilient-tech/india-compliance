import json
from contextlib import contextmanager

import frappe
from frappe.tests.utils import FrappeTestCase

from india_compliance.gst_india.utils.tests import create_transaction


@contextmanager
def toggle_seperate_advance_accounting():
    # Enable Provisional Expense
    frappe.db.set_value(
        "Company",
        "_Test Indian Registered Company",
        {
            "book_advance_payments_in_separate_party_account": 1,
            "default_advance_received_account": "Creditors - _TIRC",
        },
    )

    try:
        yield

    finally:
        frappe.db.set_value(
            "Company",
            "_Test Indian Registered Company",
            {
                "book_advance_payments_in_separate_party_account": 0,
                "default_advance_received_account": None,
            },
        )


class TestAdvancePaymentEntry(FrappeTestCase):
    EXPECTED_GL = [
        {"account": "Cash - _TIRC", "debit": 590.0, "credit": 0.0},
        {"account": "Debtors - _TIRC", "debit": 0.0, "credit": 500.0},
        {"account": "Output Tax SGST - _TIRC", "debit": 0.0, "credit": 45.0},
        {"account": "Output Tax CGST - _TIRC", "debit": 0.0, "credit": 45.0},
        {"account": "Debtors - _TIRC", "debit": 0.0, "credit": 18.0},
        {"account": "Output Tax SGST - _TIRC", "debit": 9.0, "credit": 0.0},
        {"account": "Output Tax CGST - _TIRC", "debit": 9.0, "credit": 0.0},
    ]

    def test_advance_payment_entry(self):
        payment_doc = self._create_payment_entry()
        invoice_doc = self._create_sales_invoice(payment_doc)

        # Verify outstanding amount
        outstanding_amount = frappe.db.get_value(
            "Sales Invoice", invoice_doc.name, "outstanding_amount"
        )
        self.assertEqual(outstanding_amount, 0)

        self.assertGLEntries(payment_doc, self.EXPECTED_GL)
        self.assertPLEntries(
            payment_doc,
            [
                {"amount": -100.0, "against_voucher_no": invoice_doc.name},
                {"amount": -18.0, "against_voucher_no": invoice_doc.name},
                {"amount": -400.0, "against_voucher_no": payment_doc.name},
            ],
        )

    @toggle_seperate_advance_accounting()
    def test_advance_payment_entry_with_seperate_account(self):
        payment_doc = self._create_payment_entry()
        invoice_doc = self._create_sales_invoice(payment_doc)

        # Verify outstanding amount
        outstanding_amount = frappe.db.get_value(
            "Sales Invoice", invoice_doc.name, "outstanding_amount"
        )
        self.assertEqual(outstanding_amount, 0)

        self.assertGLEntries(
            payment_doc,
            [
                {"account": "Cash - _TIRC", "debit": 590.0, "credit": 0.0},
                {"account": "Creditors - _TIRC", "debit": 0.0, "credit": 500.0},
                {"account": "Output Tax CGST - _TIRC", "debit": 0.0, "credit": 45.0},
                {"account": "Output Tax SGST - _TIRC", "debit": 0.0, "credit": 45.0},
                {"account": "Creditors - _TIRC", "debit": 100.0, "credit": 0.0},
                {"account": "Debtors - _TIRC", "debit": 0.0, "credit": 100.0},
                {"account": "Debtors - _TIRC", "debit": 0.0, "credit": 18.0},
                {"account": "Output Tax CGST - _TIRC", "debit": 9.0, "credit": 0.0},
                {"account": "Output Tax SGST - _TIRC", "debit": 9.0, "credit": 0.0},
            ],
        )
        self.assertPLEntries(
            payment_doc,
            [
                {"amount": -100.0, "against_voucher_no": invoice_doc.name},
                {"amount": -18.0, "against_voucher_no": invoice_doc.name},
                {"amount": -100.0, "against_voucher_no": payment_doc.name},
                {"amount": 400.0, "against_voucher_no": payment_doc.name},
                {"amount": 100.0, "against_voucher_no": payment_doc.name},
            ],
        )

    def test_payment_entry_allocation(self):
        payment_doc = self._create_payment_entry()
        invoice_doc = self._create_sales_invoice()

        pr = frappe.get_doc("Payment Reconciliation")
        pr.company = "_Test Indian Registered Company"
        pr.party_type = "Customer"
        pr.party = invoice_doc.customer
        pr.receivable_payable_account = invoice_doc.debit_to

        pr.get_unreconciled_entries()

        invoices = [
            row.as_dict()
            for row in pr.invoices
            if row.invoice_number == invoice_doc.name
        ]
        payments = [
            row.as_dict()
            for row in pr.payments
            if row.reference_name == payment_doc.name
        ]

        pr.allocate_entries(frappe._dict({"invoices": invoices, "payments": payments}))
        pr.reconcile()

        # Verify outstanding amount
        outstanding_amount = frappe.db.get_value(
            "Sales Invoice", invoice_doc.name, "outstanding_amount"
        )
        self.assertEqual(outstanding_amount, 0)

        self.assertGLEntries(payment_doc, self.EXPECTED_GL)
        self.assertPLEntries(
            payment_doc,
            [
                {"amount": -100.0, "against_voucher_no": invoice_doc.name},
                {"amount": -18.0, "against_voucher_no": invoice_doc.name},
                {"amount": -400.0, "against_voucher_no": payment_doc.name},
            ],
        )

    def _create_sales_invoice(self, payment_doc=None):
        invoice_doc = create_transaction(
            doctype="Sales Invoice",
            is_in_state=1,
            do_not_submit=True,
        )

        if payment_doc:
            invoice_doc.set_advances()
            for row in invoice_doc.advances:
                if row.reference_name == payment_doc.name:
                    # Allocate Net of taxes
                    row.allocated_amount = invoice_doc.net_total  # 100
                else:
                    row.allocated_amount = 0

        invoice_doc.submit()

        return invoice_doc

    def _create_payment_entry(self):
        payment_doc = create_transaction(
            doctype="Payment Entry",
            payment_type="Receive",
            mode_of_payment="Cash",
            company_address="_Test Indian Registered Company-Billing",
            party_type="Customer",
            party="_Test Registered Customer",
            customer_address="_Test Registered Customer-Billing",
            paid_to="Cash - _TIRC",
            paid_amount=500,
            is_in_state=1,
            do_not_save=True,
        )

        payment_doc.setup_party_account_field()
        payment_doc.set_missing_values()
        payment_doc.set_exchange_rate()
        payment_doc.received_amount = (
            payment_doc.paid_amount / payment_doc.target_exchange_rate
        )
        payment_doc.save()
        payment_doc.submit()

        return payment_doc

    def assertGLEntries(self, payment_doc, expected_gl_entries):
        gl_entries = frappe.get_all(
            "GL Entry",
            filters={"voucher_no": payment_doc.name},
            fields=["account", "debit", "credit"],
        )
        out_str = json.dumps(sorted(gl_entries, key=json.dumps))
        expected_out_str = json.dumps(sorted(expected_gl_entries, key=json.dumps))
        self.assertEqual(out_str, expected_out_str)

    def assertPLEntries(self, payment_doc, expected_pl_entries):
        pl_entries = frappe.get_all(
            "Payment Ledger Entry",
            filters={
                "voucher_type": payment_doc.doctype,
                "voucher_no": payment_doc.name,
            },
            fields=["amount", "against_voucher_no"],
        )
        out_str = json.dumps(sorted(pl_entries, key=json.dumps))
        expected_out_str = json.dumps(sorted(expected_pl_entries, key=json.dumps))
        self.assertEqual(out_str, expected_out_str)
