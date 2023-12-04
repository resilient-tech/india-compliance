import json
import re
from contextlib import contextmanager

import frappe
from frappe.tests.utils import FrappeTestCase
from erpnext.accounts.doctype.payment_entry.payment_entry import (
    get_outstanding_reference_documents,
)
from erpnext.accounts.doctype.unreconcile_payment.unreconcile_payment import (
    create_unreconcile_doc_for_selection,
)
from erpnext.controllers.stock_controller import show_accounting_ledger_preview

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

        # unlink payment entry
        invoice_doc.cancel()

        self.assertGLEntries(
            payment_doc,
            [
                {"account": "Cash - _TIRC", "debit": 590.0, "credit": 0.0},
                {"account": "Debtors - _TIRC", "debit": 0.0, "credit": 500.0},
                {"account": "Output Tax CGST - _TIRC", "debit": 0.0, "credit": 45.0},
                {"account": "Output Tax SGST - _TIRC", "debit": 0.0, "credit": 45.0},
            ],
        )
        self.assertPLEntries(
            payment_doc,
            [
                {"amount": -100.0, "against_voucher_no": payment_doc.name},
                {"amount": -400.0, "against_voucher_no": payment_doc.name},
            ],
        )

    def test_first_sales_then_payment_entry(self):
        invoice_doc, payment_doc = self._create_invoice_then_payment()
        payment_doc.submit()

        # Verify outstanding amount
        outstanding_amount = frappe.db.get_value(
            "Sales Invoice", invoice_doc.name, "outstanding_amount"
        )
        self.assertEqual(outstanding_amount, 0)

        self.assertGLEntries(
            payment_doc,
            [
                {"account": "Cash - _TIRC", "debit": 590.0, "credit": 0.0},
                {"account": "Debtors - _TIRC", "debit": 0.0, "credit": 100.0},
                {"account": "Debtors - _TIRC", "debit": 0.0, "credit": 400.0},
                {"account": "Output Tax SGST - _TIRC", "debit": 0.0, "credit": 45.0},
                {"account": "Output Tax CGST - _TIRC", "debit": 0.0, "credit": 45.0},
                {"account": "Debtors - _TIRC", "debit": 0.0, "credit": 18.0},
                {"account": "Output Tax SGST - _TIRC", "debit": 9.0, "credit": 0.0},
                {"account": "Output Tax CGST - _TIRC", "debit": 9.0, "credit": 0.0},
            ],
        )

        self.assertPLEntries(
            payment_doc,
            [
                {"amount": -100.0, "against_voucher_no": invoice_doc.name},
                {"amount": -18.0, "against_voucher_no": invoice_doc.name},
                {"amount": -400.0, "against_voucher_no": payment_doc.name},
            ],
        )

        # Unreconcile Payment Entry
        create_unreconcile_doc_for_selection(
            frappe.as_json(
                [
                    {
                        "company": payment_doc.company,
                        "voucher_type": payment_doc.doctype,
                        "voucher_no": payment_doc.name,
                        "against_voucher_type": invoice_doc.doctype,
                        "against_voucher_no": invoice_doc.name,
                    }
                ]
            )
        )

        self.assertGLEntries(
            payment_doc,
            [
                {"account": "Cash - _TIRC", "debit": 590.0, "credit": 0.0},
                {"account": "Debtors - _TIRC", "debit": 0.0, "credit": 100.0},
                {"account": "Debtors - _TIRC", "debit": 0.0, "credit": 400.0},
                {"account": "Output Tax CGST - _TIRC", "debit": 0.0, "credit": 45.0},
                {"account": "Output Tax SGST - _TIRC", "debit": 0.0, "credit": 45.0},
            ],
        )
        self.assertPLEntries(
            payment_doc,
            [
                {"amount": -100.0, "against_voucher_no": payment_doc.name},
                {"amount": -400.0, "against_voucher_no": payment_doc.name},
            ],
        )

    def test_preview_gl_entries(self):
        invoice_doc, payment_doc = self._create_invoice_then_payment()

        # Preview payment GL Entry
        preview_data = show_accounting_ledger_preview(
            payment_doc.company, payment_doc.doctype, payment_doc.name
        )["gl_data"]

        preview_data = [
            {"account": row[1], "debit": row[2], "credit": row[3]}
            for row in preview_data
        ]

        out_str = json.dumps(sorted(preview_data, key=json.dumps))
        expected_str = json.dumps(
            sorted(
                [
                    {"account": "Cash - _TIRC", "debit": 590.0, "credit": ""},
                    {"account": "Debtors - _TIRC", "debit": "", "credit": 100.0},
                    {"account": "Debtors - _TIRC", "debit": "", "credit": 18.0},
                    {"account": "Debtors - _TIRC", "debit": "", "credit": 400.0},
                    {"account": "Output Tax CGST - _TIRC", "debit": "", "credit": 45.0},
                    {"account": "Output Tax CGST - _TIRC", "debit": 9.0, "credit": ""},
                    {"account": "Output Tax SGST - _TIRC", "debit": "", "credit": 45.0},
                    {"account": "Output Tax SGST - _TIRC", "debit": 9.0, "credit": ""},
                ],
                key=json.dumps,
            )
        )
        self.assertEqual(out_str, expected_str)

    def validate_payment_entry_allocation(self):
        invoice_doc = self._create_sales_invoice()
        payment_doc = self._create_payment_entry(do_not_submit=True)

        args = {
            "posting_date": payment_doc.posting_date,
            "company": payment_doc.company,
            "party_type": payment_doc.party_type,
            "payment_type": payment_doc.payment_type,
            "party": payment_doc.party,
            "party_account": payment_doc.party_account,
            "from_posting_date": payment_doc.posting_date,
            "to_posting_date": payment_doc.posting_date,
        }
        references = get_outstanding_reference_documents(args)
        current_ref = next(
            ref for ref in references if ref.voucher_no == invoice_doc.name
        )

        payment_doc.extend(
            "references",
            [
                {
                    **current_ref,
                    "reference_doctype": current_ref.voucher_type,
                    "reference_name": current_ref.voucher_no,
                    "total_amount": current_ref.invoice_amount,
                    "allocated_amount": 118.0,
                }
            ],
        )

        payment_doc.save()
        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(
                r"^(Outstanding amount 118.0 is less than the total allocated amount with taxes 139.24.*)$"
            ),
            payment_doc.submit,
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
                {"amount": 500.0, "against_voucher_no": payment_doc.name},
            ],
        )

    def test_payment_entry_allocation(self):
        payment_doc = self._create_payment_entry()
        invoice_doc = self._create_sales_invoice()

        make_payment_reconciliation(payment_doc, invoice_doc, 118)

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

    def test_payment_entry_allocation_with_rounding_off(self):
        payment_doc = self._create_payment_entry()
        invoice_doc = self._create_sales_invoice()

        make_payment_reconciliation(payment_doc, invoice_doc, 50)
        make_payment_reconciliation(payment_doc, invoice_doc, 20)

        # Verify outstanding amount
        outstanding_amount = frappe.db.get_value(
            "Sales Invoice", invoice_doc.name, "outstanding_amount"
        )
        self.assertEqual(outstanding_amount, 48)

        self.assertGLEntries(
            payment_doc,
            [
                {"account": "Cash - _TIRC", "debit": 590.0, "credit": 0.0},
                # 20 / 1.18 * 0.18
                {"account": "Debtors - _TIRC", "debit": 0.0, "credit": 3.06},
                {"account": "Debtors - _TIRC", "debit": 0.0, "credit": 500.0},
                # 50 / 1.18 * 0.18
                {"account": "Debtors - _TIRC", "debit": 0.0, "credit": 7.62},
                {"account": "Output Tax CGST - _TIRC", "debit": 0.0, "credit": 45.0},
                {"account": "Output Tax CGST - _TIRC", "debit": 1.53, "credit": 0.0},
                {"account": "Output Tax CGST - _TIRC", "debit": 3.81, "credit": 0.0},
                {"account": "Output Tax SGST - _TIRC", "debit": 0.0, "credit": 45.0},
                {"account": "Output Tax SGST - _TIRC", "debit": 1.53, "credit": 0.0},
                {"account": "Output Tax SGST - _TIRC", "debit": 3.81, "credit": 0.0},
            ],
        )
        self.assertPLEntries(
            payment_doc,
            [
                {"amount": -16.95, "against_voucher_no": invoice_doc.name},
                {"amount": -3.06, "against_voucher_no": invoice_doc.name},
                {"amount": -42.37, "against_voucher_no": invoice_doc.name},
                {"amount": -7.62, "against_voucher_no": invoice_doc.name},
                # 500 - 16.95 - 42.37
                {"amount": -440.68, "against_voucher_no": payment_doc.name},
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

    def _create_payment_entry(self, do_not_submit=False):
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

        if not do_not_submit:
            payment_doc.submit()

        return payment_doc

    def _create_invoice_then_payment(self):
        invoice_doc = self._create_sales_invoice()
        payment_doc = self._create_payment_entry(do_not_submit=True)

        args = {
            "posting_date": payment_doc.posting_date,
            "company": payment_doc.company,
            "party_type": payment_doc.party_type,
            "payment_type": payment_doc.payment_type,
            "party": payment_doc.party,
            "party_account": payment_doc.party_account,
            "from_posting_date": payment_doc.posting_date,
            "to_posting_date": payment_doc.posting_date,
        }
        references = get_outstanding_reference_documents(args)
        current_ref = next(
            ref for ref in references if ref.voucher_no == invoice_doc.name
        )

        payment_doc.extend(
            "references",
            [
                {
                    **current_ref,
                    "reference_doctype": current_ref.voucher_type,
                    "reference_name": current_ref.voucher_no,
                    "total_amount": current_ref.invoice_amount,
                    "allocated_amount": 100.0,
                }
            ],
        )

        payment_doc.save()

        return invoice_doc, payment_doc

    def assertGLEntries(self, payment_doc, expected_gl_entries):
        gl_entries = frappe.get_all(
            "GL Entry",
            filters={"voucher_no": payment_doc.name, "is_cancelled": 0},
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
                "delinked": 0,
            },
            fields=["amount", "against_voucher_no"],
        )
        out_str = json.dumps(sorted(pl_entries, key=json.dumps))
        expected_out_str = json.dumps(sorted(expected_pl_entries, key=json.dumps))
        self.assertEqual(out_str, expected_out_str)


def make_payment_reconciliation(payment_doc, invoice_doc, amount):
    pr = frappe.get_doc("Payment Reconciliation")
    pr.company = "_Test Indian Registered Company"
    pr.party_type = "Customer"
    pr.party = invoice_doc.customer
    pr.receivable_payable_account = invoice_doc.debit_to

    pr.get_unreconciled_entries()
    invoices = [
        row.as_dict() for row in pr.invoices if row.invoice_number == invoice_doc.name
    ]
    payments = [
        row.as_dict() for row in pr.payments if row.reference_name == payment_doc.name
    ]

    pr.allocate_entries(frappe._dict({"invoices": invoices, "payments": payments}))
    pr.allocation[0].allocated_amount = amount
    pr.reconcile()
