import json
import re
from contextlib import contextmanager
from typing import ClassVar

import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import (
    get_outstanding_reference_documents,
)
from erpnext.accounts.doctype.payment_reconciliation.payment_reconciliation import (
    adjust_allocations_for_taxes,
)
from erpnext.accounts.doctype.unreconcile_payment.unreconcile_payment import (
    create_unreconcile_doc_for_selection,
)
from erpnext.controllers.accounts_controller import (
    get_advance_payment_entries_for_regional,
)
from erpnext.controllers.stock_controller import show_accounting_ledger_preview
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, getdate

from india_compliance.gst_india.utils.gstr_1 import GSTR1_DataField as inv_f
from india_compliance.gst_india.utils.gstr_1.gstr_1_json_map import GSTR1BooksData
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
    EXPECTED_GL: ClassVar[list] = [
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
        outstanding_amount = frappe.db.get_value("Sales Invoice", invoice_doc.name, "outstanding_amount")
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

    def test_advance_payment_entry_with_returns(self):
        payment_doc = self._create_payment_entry()
        invoice_doc = self._create_sales_invoice(payment_doc)

        create_transaction(
            doctype="Sales Invoice",
            is_in_state=1,
            is_return=1,
            qty=-1,
            return_against=invoice_doc.name,
        )

        self.assertGLEntries(payment_doc, self.EXPECTED_GL)

    def test_first_sales_then_payment_entry(self):
        invoice_doc, payment_doc = self._create_invoice_then_payment()
        payment_doc.submit()

        # Verify outstanding amount
        outstanding_amount = frappe.db.get_value("Sales Invoice", invoice_doc.name, "outstanding_amount")
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
        _, payment_doc = self._create_invoice_then_payment()

        # Preview payment GL Entry
        preview_data = show_accounting_ledger_preview(
            payment_doc.company, payment_doc.doctype, payment_doc.name
        )["gl_data"]

        preview_data = [{"account": row[1], "debit": row[2], "credit": row[3]} for row in preview_data]

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

    def test_over_allocated_advance_payment_raises(self):
        # allocating more than the invoice outstanding (incl. the GST reversal) must raise
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
        current_ref = next(ref for ref in references if ref.voucher_no == invoice_doc.name)

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
        outstanding_amount = frappe.db.get_value("Sales Invoice", invoice_doc.name, "outstanding_amount")
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
        outstanding_amount = frappe.db.get_value("Sales Invoice", invoice_doc.name, "outstanding_amount")
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

        payment_entries = get_advance_payment_entries_for_regional(
            party_type="Customer",
            party=payment_doc.party,
            party_account=[payment_doc.paid_from],
            order_list=[],
            order_doctype="Sales Order",
            include_unallocated=True,
            condition=frappe._dict({"company": payment_doc.company, "name": payment_doc.name}),
        )

        self.assertEqual(flt(payment_entries[0].amount, 2), 540.01)

        make_payment_reconciliation(payment_doc, invoice_doc, 20)

        # Verify outstanding amount
        outstanding_amount = frappe.db.get_value("Sales Invoice", invoice_doc.name, "outstanding_amount")
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

    def test_payment_entry_allocation_with_inclusive_tax_invoice(self):
        """
        Reconcile an advance payment (with GST) against a tax-inclusive
        Sales Invoice.
        """
        payment_doc = self._create_payment_entry()
        invoice_doc = self._create_inclusive_sales_invoice()

        # invoice: rate 100 inclusive of 18% GST => net 84.75, tax 15.25, grand total 100
        self.assertEqual(invoice_doc.grand_total, 100)
        self.assertEqual(invoice_doc.outstanding_amount, 100)

        # Should reconcile without raising.
        make_payment_reconciliation(payment_doc, invoice_doc, 100)

        # A clean fix needs ERPNext to derive the net allocation/tax split together so this rounding
        # difference is absorbed into the net amount instead of being left in outstanding.
        outstanding_amount = frappe.db.get_value("Sales Invoice", invoice_doc.name, "outstanding_amount")
        self.assertEqual(flt(outstanding_amount, 2), -0.01)

    def _create_inclusive_sales_invoice(self):
        invoice_doc = create_transaction(
            doctype="Sales Invoice",
            is_in_state=1,
            do_not_save=True,
        )
        for tax in invoice_doc.taxes:
            tax.included_in_print_rate = 1

        invoice_doc.submit()

        return invoice_doc

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
        payment_doc.received_amount = payment_doc.paid_amount / payment_doc.target_exchange_rate
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
        current_ref = next(ref for ref in references if ref.voucher_no == invoice_doc.name)

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


class TestRegionalOverrides(TestAdvancePaymentEntry):
    def test_get_advance_payment_entries_for_regional(self):
        payment_doc = self._create_payment_entry()
        invoice_doc = self._create_sales_invoice(payment_doc)

        conditions = frappe._dict({"company": invoice_doc.get("company")})

        payment_entry = get_advance_payment_entries_for_regional(
            party_type="Customer",
            party=invoice_doc.customer,
            party_account=[invoice_doc.debit_to],
            order_list=[],
            order_doctype="Sales Order",
            include_unallocated=True,
            condition=conditions,
        )

        payment_entry_amount = payment_entry[0].get("amount")
        self.assertNotEqual(400, payment_entry_amount)

    def test_get_advance_payment_entries_for_regional_with_gst_accounts_in_deduction_table(
        self,
    ):
        payment_doc = self._create_payment_entry(do_not_submit=True)
        payment_doc.taxes = []
        payment_doc.append(
            "deductions",
            {
                "account": "Output Tax CGST - _TIRC",
                "cost_center": "Main - _TIRC",
                "amount": 45,
            },
        )
        payment_doc.append(
            "deductions",
            {
                "account": "Output Tax SGST - _TIRC",
                "cost_center": "Main - _TIRC",
                "amount": 45,
            },
        )
        payment_doc.submit()
        self.assertEqual(payment_doc.total_taxes_and_charges, 0)
        invoice_doc = self._create_sales_invoice(payment_doc)

        conditions = frappe._dict({"company": invoice_doc.get("company"), "name": payment_doc.name})

        payment_entry = get_advance_payment_entries_for_regional(
            party_type="Customer",
            party=invoice_doc.customer,
            party_account=[invoice_doc.debit_to],
            order_list=[],
            order_doctype="Sales Order",
            include_unallocated=True,
            condition=conditions,
        )

        payment_entry_amount = payment_entry[0].get("amount")
        # Total Unallocated = 500+90 =>590
        # Remaining Unallocated = 590 - 100 (sales invoice amount)
        self.assertEqual(490, payment_entry_amount)

    def test_get_advance_payment_entries_for_regional_grosses_up_once_per_payment(self):
        """An advance partly earmarked against a Sales Order comes back as two rows -- one for the
        order reference, one for the unallocated balance.Reversal should be proportionate"""
        sales_order = create_transaction(doctype="Sales Order", is_in_state=1)
        payment_doc = self._create_payment_entry(do_not_submit=True)
        payment_doc.append(
            "references",
            {
                "reference_doctype": sales_order.doctype,
                "reference_name": sales_order.name,
                "total_amount": sales_order.grand_total,
                "outstanding_amount": sales_order.grand_total,
                "allocated_amount": 100,
            },
        )
        payment_doc.save()
        payment_doc.submit()

        payment_entries = get_advance_payment_entries_for_regional(
            party_type="Customer",
            party=payment_doc.party,
            party_account=[payment_doc.paid_from],
            order_list=[],
            order_doctype="Sales Order",
            include_unallocated=True,
            against_all_orders=True,
            condition=frappe._dict({"company": payment_doc.company, "name": payment_doc.name}),
        )

        self.assertEqual([row.amount for row in payment_entries], [118.0, 472.0])

    def test_adjust_allocations_for_taxes(self):
        payment_doc = self._create_payment_entry()
        invoice_doc = self._create_sales_invoice()

        pr = frappe.get_doc("Payment Reconciliation")
        pr.company = "_Test Indian Registered Company"
        pr.party_type = "Customer"
        pr.party = invoice_doc.customer
        pr.receivable_payable_account = invoice_doc.debit_to

        pr.get_unreconciled_entries()
        invoices = [row.as_dict() for row in pr.invoices if row.invoice_number == invoice_doc.name]
        payments = [row.as_dict() for row in pr.payments if row.reference_name == payment_doc.name]
        pr.allocate_entries(frappe._dict({"invoices": invoices, "payments": payments}))
        pr.allocation[0].allocated_amount = 50

        adjust_allocations_for_taxes(pr)
        self.assertEqual(pr.allocation[0].allocated_amount, 42.37)  # 50 / 1.18


def make_payment_reconciliation(payment_doc, invoice_doc, amount):
    pr = frappe.get_doc("Payment Reconciliation")
    pr.company = "_Test Indian Registered Company"
    pr.party_type = "Customer"
    pr.party = invoice_doc.customer
    pr.receivable_payable_account = invoice_doc.debit_to

    pr.get_unreconciled_entries()
    invoices = [row.as_dict() for row in pr.invoices if row.invoice_number == invoice_doc.name]
    payments = [row.as_dict() for row in pr.payments if row.reference_name == payment_doc.name]

    pr.allocate_entries(frappe._dict({"invoices": invoices, "payments": payments}))
    pr.allocation[0].allocated_amount = amount
    pr.reconcile()


# ---------------------------------------------------------------------------
# Full matrix: payment {inclusive, exclusive} x invoice {inclusive, exclusive}
# x flow {reconciliation tool, advance-in-invoice}.
#
# Every cell is the SAME economic event, so a correct implementation must produce
# identical ledgers however tax-inclusivity is entered:
#   advance: base 500 + 18% GST = 590 cash  (excl: paid 500 + tax; incl: paid 590 carved)
#   invoice: net 100 + 18% GST = 118 grand   (excl: rate 100 + tax; incl: rate 118 carved)
# Full reconcile consumes 100 of base, reverses 90*100/500 = 18 GST exactly, 400 left.
# ---------------------------------------------------------------------------

# net (debit - credit) per account on the Payment Entry after a full reconcile
MATRIX_RECONCILED_GL: dict = {
    "Cash - _TIRC": 590.0,  # full cash received: 500 base + 90 GST
    "Debtors - _TIRC": -518.0,  # 500 advance + 18 GST reversal (both credits)
    "Output Tax CGST - _TIRC": -36.0,  # 45 charged on advance - 9 reversed
    "Output Tax SGST - _TIRC": -36.0,
}
# separate-account variant (book_advance_payments_in_separate_party_account)
MATRIX_RECONCILED_GL_SEPARATE: dict = {
    "Cash - _TIRC": 590.0,
    "Creditors - _TIRC": -400.0,  # 500 advance liability - 100 reclassed to receivable
    "Debtors - _TIRC": -118.0,  # 100 reclass + 18 GST reversal
    "Output Tax CGST - _TIRC": -36.0,
    "Output Tax SGST - _TIRC": -36.0,
}


class TestPaymentReconciliationMatrix(FrappeTestCase):
    # ---- the 8 core cells (no separate party account) ----

    def test_excl_payment_excl_invoice_via_reconcile_tool(self):
        self._run_cell(payment_inclusive=False, invoice_inclusive=False, flow="reconcile_tool")

    def test_excl_payment_excl_invoice_via_advance_in_invoice(self):
        self._run_cell(payment_inclusive=False, invoice_inclusive=False, flow="advance_in_invoice")

    def test_excl_payment_incl_invoice_via_reconcile_tool(self):
        self._run_cell(payment_inclusive=False, invoice_inclusive=True, flow="reconcile_tool")

    def test_excl_payment_incl_invoice_via_advance_in_invoice(self):
        self._run_cell(payment_inclusive=False, invoice_inclusive=True, flow="advance_in_invoice")

    def test_incl_payment_excl_invoice_via_reconcile_tool(self):
        self._run_cell(payment_inclusive=True, invoice_inclusive=False, flow="reconcile_tool")

    def test_incl_payment_excl_invoice_via_advance_in_invoice(self):
        self._run_cell(payment_inclusive=True, invoice_inclusive=False, flow="advance_in_invoice")

    def test_incl_payment_incl_invoice_via_reconcile_tool(self):
        self._run_cell(payment_inclusive=True, invoice_inclusive=True, flow="reconcile_tool")

    def test_incl_payment_incl_invoice_via_advance_in_invoice(self):
        self._run_cell(payment_inclusive=True, invoice_inclusive=True, flow="advance_in_invoice")

    # ---- representative separate-party-account coverage ----

    @toggle_seperate_advance_accounting()
    def test_separate_account_excl_payment_via_advance_in_invoice(self):
        self._run_cell(
            payment_inclusive=False,
            invoice_inclusive=False,
            flow="advance_in_invoice",
            reconciled_gl=MATRIX_RECONCILED_GL_SEPARATE,
            pe_pl=400.0,
        )

    @toggle_seperate_advance_accounting()
    def test_separate_account_incl_payment_via_advance_in_invoice(self):
        self._run_cell(
            payment_inclusive=True,
            invoice_inclusive=False,
            flow="advance_in_invoice",
            reconciled_gl=MATRIX_RECONCILED_GL_SEPARATE,
            pe_pl=400.0,
        )

    def test_multiple_advances_in_one_invoice(self):
        # two advances (one exclusive, one inclusive) fully cover one invoice via the
        # advances table; the per-reference reversal + over-allocation check must hold
        # for each reference (the cells above cover only a single advance)
        pay_excl = self._matrix_payment(inclusive=False)
        pay_incl = self._matrix_payment(inclusive=True)

        # invoice net 200 + 18% GST = 236 grand; allocate net 100 from each advance
        invoice_doc = create_transaction(doctype="Sales Invoice", is_in_state=1, rate=200, do_not_save=True)
        invoice_doc.save()
        invoice_doc.set_advances()
        for row in invoice_doc.advances:
            row.allocated_amount = 100 if row.reference_name in (pay_excl.name, pay_incl.name) else 0
        invoice_doc.submit()

        self.assertEqual(flt(invoice_doc.net_total, 2), 200.0)
        self.assertEqual(
            flt(frappe.db.get_value("Sales Invoice", invoice_doc.name, "outstanding_amount"), 2),
            0.0,
            "invoice should be fully cleared by both advances",
        )
        # each advance reverses its own proportional GST (90 * 100 / 500 = 18 each)
        for pay in (pay_excl, pay_incl):
            refs = [
                r
                for r in frappe.get_doc("Payment Entry", pay.name).references
                if r.reference_name == invoice_doc.name
            ]
            self.assertEqual(len(refs), 1)
            self.assertEqual(flt(refs[0].allocated_amount, 2), 100.0)

    # ---- shared workflow ----

    def _run_cell(
        self,
        payment_inclusive,
        invoice_inclusive,
        flow,
        reconciled_gl=None,
        inv_pl=-118.0,
        pe_pl=-400.0,
    ):
        reconciled_gl = reconciled_gl or MATRIX_RECONCILED_GL

        payment_doc = self._matrix_payment(inclusive=payment_inclusive)
        # economic setup sanity: both inclusive and exclusive advances are base 500 + GST 90
        self.assertEqual(flt(payment_doc.total_taxes_and_charges, 2), 90.0, "advance GST should be 90")
        self.assertEqual(flt(payment_doc.unallocated_amount, 2), 500.0, "advance base should be 500")

        # snapshot the pure-advance ledgers to assert the unreconcile round-trip later
        advance_gl = self._gl_net_by_account(payment_doc)
        advance_pl = self._pl_net_by_voucher(payment_doc)

        if flow == "advance_in_invoice":
            invoice_doc = self._matrix_invoice(inclusive=invoice_inclusive, advance_payment=payment_doc)
        else:
            invoice_doc = self._matrix_invoice(inclusive=invoice_inclusive)
            make_payment_reconciliation(payment_doc, invoice_doc, invoice_doc.grand_total)

        self.assertEqual(flt(invoice_doc.net_total, 2), 100.0, "invoice net should be 100")
        self.assertEqual(flt(invoice_doc.grand_total, 2), 118.0, "invoice grand total should be 118")

        # --- fully reconciled state ---
        self.assertEqual(
            flt(frappe.db.get_value("Sales Invoice", invoice_doc.name, "outstanding_amount"), 2),
            0.0,
            "invoice should be fully reconciled",
        )

        refs = [
            r
            for r in frappe.get_doc("Payment Entry", payment_doc.name).references
            if r.reference_name == invoice_doc.name
        ]
        self.assertEqual(len(refs), 1, "expected exactly one PE reference to the invoice")
        self.assertEqual(flt(refs[0].allocated_amount, 2), 100.0, "reference allocated should be net 100")
        self.assertEqual(flt(refs[0].total_amount, 2), 118.0, "reference total should be grand 118")

        self.assertEqual(self._gl_net_by_account(payment_doc), reconciled_gl)
        self.assertEqual(
            self._pl_net_by_voucher(payment_doc),
            {invoice_doc.name: inv_pl, payment_doc.name: pe_pl},
        )

        # --- GSTR-1 advance reporting (11A received / 11B adjusted) ---
        # taxable values must be NET of GST however inclusivity is entered:
        # 11A = full advance base 500 @ 18%; 11B = net adjusted 100 @ 18% (negative).
        # (gross paid 590 of an inclusive advance would wrongly report rate 15%.)
        self._assert_advance_report(payment_doc, received=500.0, adjusted=-100.0)

        # --- unreconcile round-trip: ledgers return to the pure-advance snapshot ---
        self._unreconcile(payment_doc, invoice_doc)
        self.assertEqual(self._gl_net_by_account(payment_doc), advance_gl, "GL should revert on unreconcile")
        self.assertEqual(self._pl_net_by_voucher(payment_doc), advance_pl, "PL should revert on unreconcile")
        self.assertEqual(
            flt(frappe.db.get_value("Sales Invoice", invoice_doc.name, "outstanding_amount"), 2),
            118.0,
            "invoice outstanding should be restored on unreconcile",
        )

        # 11A still shows the (now partly adjusted) advance; the 11B adjustment is gone
        self._assert_advance_report(payment_doc, received=500.0, adjusted=None)

    # ---- builders ----

    def _matrix_payment(self, inclusive=False):
        paid_amount = 590 if inclusive else 500
        payment_doc = create_transaction(
            doctype="Payment Entry",
            payment_type="Receive",
            mode_of_payment="Cash",
            company_address="_Test Indian Registered Company-Billing",
            party_type="Customer",
            party="_Test Registered Customer",
            customer_address="_Test Registered Customer-Billing",
            paid_to="Cash - _TIRC",
            paid_amount=paid_amount,
            is_in_state=1,
            do_not_save=True,
        )
        if inclusive:
            for tax in payment_doc.taxes:
                tax.included_in_paid_amount = 1

        payment_doc.setup_party_account_field()
        payment_doc.set_missing_values()
        payment_doc.set_exchange_rate()
        payment_doc.received_amount = payment_doc.paid_amount / payment_doc.target_exchange_rate
        payment_doc.save()
        payment_doc.submit()

        return payment_doc

    def _matrix_invoice(self, inclusive=False, advance_payment=None):
        # exclusive: rate 100 + 18% on top; inclusive: rate 118 with tax embedded -> net 100
        rate = 118 if inclusive else 100
        invoice_doc = create_transaction(
            doctype="Sales Invoice",
            is_in_state=1,
            rate=rate,
            do_not_save=True,
        )
        if inclusive:
            for tax in invoice_doc.taxes:
                tax.included_in_print_rate = 1

        invoice_doc.save()

        if advance_payment:
            invoice_doc.set_advances()
            for row in invoice_doc.advances:
                row.allocated_amount = (
                    invoice_doc.net_total if row.reference_name == advance_payment.name else 0
                )

        invoice_doc.submit()

        return invoice_doc

    def _unreconcile(self, payment_doc, invoice_doc):
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

    # ---- GSTR-1 advance reporting helpers (11A received / 11B adjusted) ----

    def _assert_advance_report(self, payment_doc, received, adjusted):
        books = GSTR1BooksData(
            filters=frappe._dict(
                company=payment_doc.company,
                company_gstin=payment_doc.company_gstin,
                from_date=getdate(),
                to_date=getdate(),
            )
        )

        # 11A Advances Received: full advance base, reported net of GST
        self._assert_advance_row(books.prepare_advances_recevied_data(), payment_doc.name, received)
        # 11B Advances Adjusted: net adjusted base, reported negative
        self._assert_advance_row(books.prepare_advances_adjusted_data(), payment_doc.name, adjusted)

    def _assert_advance_row(self, prepared, payment_name, taxable_value):
        row = next(
            (r for rows in prepared.values() for r in rows if r[inv_f.DOC_NUMBER] == payment_name),
            None,
        )

        if taxable_value is None:
            self.assertIsNone(row, f"no advance row expected for {payment_name}")
            return

        self.assertIsNotNone(row, f"advance row expected for {payment_name}")
        self.assertEqual(row[inv_f.TAX_RATE], 18)
        self.assertEqual(flt(row[inv_f.TAXABLE_VALUE], 2), taxable_value)
        # intra-state @ 18% => CGST 9% + SGST 9%, no IGST/cess
        self.assertEqual(flt(row[inv_f.CGST], 2), flt(taxable_value * 0.09, 2))
        self.assertEqual(flt(row[inv_f.SGST], 2), flt(taxable_value * 0.09, 2))
        self.assertEqual(flt(row[inv_f.IGST], 2), 0.0)
        self.assertEqual(flt(row[inv_f.CESS], 2), 0.0)

    # ---- ledger helpers (net per account / per against-voucher, drops zero nets) ----

    def _gl_net_by_account(self, payment_doc):
        rows = frappe.get_all(
            "GL Entry",
            filters={"voucher_no": payment_doc.name, "is_cancelled": 0},
            fields=["account", "debit", "credit"],
        )
        net = {}
        for row in rows:
            net[row.account] = flt(net.get(row.account, 0) + row.debit - row.credit, 2)
        return {account: amount for account, amount in net.items() if amount}

    def _pl_net_by_voucher(self, payment_doc):
        rows = frappe.get_all(
            "Payment Ledger Entry",
            filters={"voucher_type": payment_doc.doctype, "voucher_no": payment_doc.name, "delinked": 0},
            fields=["against_voucher_no", "amount"],
        )
        net = {}
        for row in rows:
            net[row.against_voucher_no] = flt(net.get(row.against_voucher_no, 0) + row.amount, 2)
        return {voucher: amount for voucher, amount in net.items() if amount}
