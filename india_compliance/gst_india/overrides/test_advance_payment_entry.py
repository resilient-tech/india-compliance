import json

import frappe
from frappe.tests.utils import FrappeTestCase

from india_compliance.gst_india.utils.tests import create_transaction


class TestAdvancePaymentEntry(FrappeTestCase):
    EXPECTED_GL = [
        {"account": "Cash - _TIRC", "debit": 11800.0, "credit": 0.0},
        {"account": "Debtors - _TIRC", "debit": 0.0, "credit": 10000.0},
        {"account": "Output Tax SGST - _TIRC", "debit": 0.0, "credit": 900.0},
        {"account": "Output Tax CGST - _TIRC", "debit": 0.0, "credit": 900.0},
        {"account": "Debtors - _TIRC", "debit": 0.0, "credit": 18.0},
        {"account": "Output Tax SGST - _TIRC", "debit": 9.0, "credit": 0.0},
        {"account": "Output Tax CGST - _TIRC", "debit": 9.0, "credit": 0.0},
    ]

    def test_advance_payment_entry(self):
        payment_doc = self._create_payment_entry()
        self._create_sales_invoice(payment_doc)

        # Assert GL Entries for Payment Entry
        self.assertGLEntries(payment_doc, self.EXPECTED_GL)

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

        self.assertGLEntries(payment_doc, self.EXPECTED_GL)

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
            paid_amount=10000,
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
