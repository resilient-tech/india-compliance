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
from india_compliance.tests.erpnext_test_utils import create_account


@contextmanager
def toggle_seperate_advance_accounting(advance_account="Creditors - _TIRC"):
    # Enable Provisional Expense
    frappe.db.set_value(
        "Company",
        "_Test Indian Registered Company",
        {
            "book_advance_payments_in_separate_party_account": 1,
            "default_advance_received_account": advance_account,
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
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(frappe.db.rollback)

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
                r"^(Outstanding amount 118.0 INR is less than the total allocated amount with taxes 139.24 INR.*)$"
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

    def test_single_invoice_reconciled_in_parts(self):
        payment_doc = self._create_payment_entry()  # 500 + 90 GST
        invoice_doc = create_transaction(doctype="Sales Invoice", is_in_state=1, rate=500)
        self.assertEqual(flt(invoice_doc.grand_total, 2), 590.0)

        make_payment_reconciliation(payment_doc, invoice_doc, 300)
        make_payment_reconciliation(payment_doc, invoice_doc, 290)

        payment_doc.reload()
        self.assertEqual(flt(payment_doc.unallocated_amount, 2), 0.0, "advance fully consumed")
        self.assertEqual([flt(row.allocated_amount, 2) for row in payment_doc.references], [254.24, 245.76])
        self.assertEqual(
            flt(frappe.db.get_value("Sales Invoice", invoice_doc.name, "outstanding_amount"), 2), 0.0
        )

        # 45.76 reversed with the first part and 44.24 with the second: all 90 comes back, so the
        # GST accounts net to nothing and the receivable carries the whole 590
        net = {}
        for row in frappe.get_all(
            "GL Entry",
            filters={"voucher_no": payment_doc.name, "is_cancelled": 0},
            fields=["account", "debit", "credit"],
        ):
            net[row.account] = flt(net.get(row.account, 0) + row.debit - row.credit, 2)

        self.assertEqual(net["Debtors - _TIRC"], -590.0)
        self.assertEqual(net["Output Tax CGST - _TIRC"], 0.0)
        self.assertEqual(net["Output Tax SGST - _TIRC"], 0.0)

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


class LedgerNetMixin:
    """Net ledger / GSTR-1 advance assertions shared by the single- and multi-currency suites."""

    def _advance_detail_summary(self, payment_doc):
        from india_compliance.gst_india.report.gst_advance_detail.gst_advance_detail import (
            execute as advance_detail,
        )

        _columns, data = advance_detail(
            frappe._dict(
                company=payment_doc.company,
                company_gstin=payment_doc.company_gstin,
                from_date=getdate(),
                to_date=getdate(),
                show_for_period=1,
                show_summary=1,
            )
        )
        return next(row for row in data if row.get("payment_entry") == payment_doc.name)

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


class TestPaymentReconciliationMatrix(LedgerNetMixin, FrappeTestCase):
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


# Multi-currency: the same economic event as the matrix above, transacted in USD on a
# USD receivable at a round rate. Base (INR) ledgers must be identical; only the
# account-currency amounts differ. Advance: 5 USD (base 500) + 90 GST INR.
# Invoice: net 1 USD (base 100) + 18% => 1.18 USD grand. Reversal: 18 INR / 0.18 USD.
# ---------------------------------------------------------------------------

FX_RATE = 100
USD_DEBTORS = "Debtors USD - _TIRC"

# identical to MATRIX_RECONCILED_GL except the receivable is the USD account
FX_RECONCILED_GL: dict = {
    "Cash - _TIRC": 590.0,  # full cash received: 500 base + 90 GST (INR)
    USD_DEBTORS: -518.0,  # 500 advance + 18 GST reversal (both credits)
    "Output Tax CGST - _TIRC": -36.0,  # 45 charged on advance - 9 reversed
    "Output Tax SGST - _TIRC": -36.0,
}


class TestMultiCurrencyReconciliation(LedgerNetMixin, FrappeTestCase):
    def test_fx_excl_payment_via_reconcile_tool(self):
        self._assert_fx_cell(payment_inclusive=False, flow="reconcile_tool")

    def test_fx_incl_payment_via_reconcile_tool(self):
        self._assert_fx_cell(payment_inclusive=True, flow="reconcile_tool")

    def test_fx_excl_payment_via_advance_in_invoice(self):
        self._assert_fx_cell(payment_inclusive=False, flow="advance_in_invoice")

    def test_fx_incl_payment_via_advance_in_invoice(self):
        self._assert_fx_cell(payment_inclusive=True, flow="advance_in_invoice")

    def test_fx_over_allocated_advance_payment_raises(self):
        """The advances-table guard must compare like with like: allocated_amount is in the party
        account currency, so a foreign-currency invoice has to be checked against its own grand
        total, not the base one (against which nothing ever looks over-allocated)."""
        payment_doc = self._fx_payment()

        invoice_doc = create_transaction(
            doctype="Sales Invoice",
            customer=self._usd_customer(),
            currency="USD",
            conversion_rate=FX_RATE,
            debit_to=self._usd_debtors(),
            is_in_state=1,
            rate=1,
            do_not_save=True,
        )
        invoice_doc.save()
        self.assertEqual(flt(invoice_doc.grand_total, 2), 1.18)

        invoice_doc.set_advances()
        for row in invoice_doc.advances:
            # ERPNext allows allocating the full grand total; it is the GST reversal on top
            # (1.18 + 0.21 = 1.39 > 1.18 USD) that over-allocates, which is IC's guard to catch
            row.allocated_amount = invoice_doc.grand_total if row.reference_name == payment_doc.name else 0

        self.assertRaisesRegex(
            frappe.ValidationError,
            "Allocated amount with taxes",
            invoice_doc.submit,
        )

    def test_fx_invoice_booked_at_a_different_rate(self):
        """An advance received at one rate, adjusted against an invoice raised at another.
        erpnext books the exchange difference onto the reference row, and once it does it stops
        refreshing that row's reference details -- leaving outstanding_amount unset."""
        payment_doc = self._fx_payment()  # 5 USD @ 100 -> base 500 + 90 GST
        invoice_doc = self._fx_invoice(conversion_rate=90)  # 1.18 USD @ 90 -> base 106.20

        make_payment_reconciliation(payment_doc, invoice_doc, invoice_doc.grand_total)

        self.assertEqual(
            flt(frappe.db.get_value("Sales Invoice", invoice_doc.name, "outstanding_amount"), 2), 0.0
        )

        # the liability was booked at 100, so it has to be cleared at 100 -- not at the
        # invoice's rate, which would strand a stub in the GST accounts forever
        reversal = frappe.get_all(
            "GL Entry",
            filters={
                "voucher_no": payment_doc.name,
                "account": USD_DEBTORS,
                "against_voucher": invoice_doc.name,
                "remarks": ["like", "Reversal for GST%"],
                "is_cancelled": 0,
            },
            fields=["credit", "credit_in_account_currency"],
        )
        self.assertEqual(len(reversal), 1)
        self.assertEqual(flt(reversal[0].credit, 2), 18.0)
        self.assertEqual(flt(reversal[0].credit_in_account_currency, 2), 0.18)

        # 11B reports the adjustment at the advance's rate, so the rate bucket stays 18%
        self._assert_advance_report(payment_doc, received=500.0, adjusted=-100.0)

        self._assert_gst_difference_left_in_receivable(payment_doc, invoice_doc, -401.8)

    def test_fx_invoice_at_a_different_rate_via_advance_in_invoice(self):
        """The same two rates through the advances table instead of the reconciliation tool.
        This flow never hit the crash, so it must come out exactly as the reconcile-tool one."""
        payment_doc = self._fx_payment()
        invoice_doc = self._fx_invoice(advance_payment=payment_doc, conversion_rate=90)

        self.assertEqual(
            flt(frappe.db.get_value("Sales Invoice", invoice_doc.name, "outstanding_amount"), 2), 0.0
        )
        self.assertEqual(self._gst_reversal(payment_doc, invoice_doc), (18.0, 0.18))
        self._assert_gst_difference_left_in_receivable(payment_doc, invoice_doc, -401.8)

    def test_fx_invoice_at_a_higher_rate(self):
        """Rate moves the other way: erpnext books a loss on the goods, and the GST slice's
        difference lands with the opposite sign -- still in the receivable."""
        payment_doc = self._fx_payment()
        invoice_doc = self._fx_invoice(conversion_rate=110)  # 1.18 USD @ 110 -> base 129.80

        make_payment_reconciliation(payment_doc, invoice_doc, invoice_doc.grand_total)

        # cleared at the advance's rate regardless of which way the rate moved
        self.assertEqual(self._gst_reversal(payment_doc, invoice_doc), (18.0, 0.18))
        # -500 + 129.80 - 18 - 10 (erpnext's loss) = -398.20, i.e. 1.80 the other way
        self._assert_gst_difference_left_in_receivable(
            payment_doc, invoice_doc, -398.2, exchange_gain_loss=-10.0
        )

    def test_fx_three_invoices_against_one_advance(self):
        """The multi-invoice repro on a USD advance: the reconciliation tool's gross-up has to
        be converted to the party account currency before it is added to the offered amount."""
        payment_doc = self._fx_payment()

        # the balance the tool offers must be the advance grossed up by its pending GST,
        # converted to the party account currency: 5 USD + 90 INR / 100 = 5.90 USD
        offered = get_advance_payment_entries_for_regional(
            party_type="Customer",
            party=payment_doc.party,
            party_account=[payment_doc.paid_from],
            order_list=[],
            order_doctype="Sales Order",
            include_unallocated=True,
            condition=frappe._dict({"company": payment_doc.company, "name": payment_doc.name}),
        )
        self.assertEqual([flt(row.amount, 2) for row in offered], [5.9])

        invoices = [self._fx_invoice() for _ in range(5)]

        for invoice_doc in invoices:
            make_payment_reconciliation(payment_doc, invoice_doc, invoice_doc.grand_total)

        payment_doc.reload()
        self.assertEqual(flt(payment_doc.unallocated_amount, 2), 0.0, "advance should be exactly consumed")

        references = {row.reference_name: row for row in payment_doc.references}
        for invoice_doc in invoices:
            self.assertEqual(
                flt(frappe.db.get_value("Sales Invoice", invoice_doc.name, "outstanding_amount"), 2),
                0.0,
                f"{invoice_doc.name} should be fully settled",
            )
            self.assertEqual(flt(references[invoice_doc.name].allocated_amount, 2), 1.0)

        # 90 GST charged, all reversed 18 at a time -> GST accounts net to zero and drop out
        self.assertEqual(
            self._gl_net_by_account(payment_doc),
            {"Cash - _TIRC": 590.0, USD_DEBTORS: -590.0},
        )

    # ---- shared workflow ----

    def _assert_fx_cell(self, payment_inclusive, flow):
        payment_doc = self._fx_payment(inclusive=payment_inclusive)
        # economic setup in base currency: net taxable 500 + 90 GST, transacted in USD.
        # net base is 500 for both inclusive (590 gross - 90 embedded) and exclusive (500).
        self.assertEqual(payment_doc.paid_from_account_currency, "USD")
        self.assertEqual(flt(payment_doc.base_total_taxes_and_charges, 2), 90.0, "advance GST is 90 INR")

        if flow == "advance_in_invoice":
            invoice_doc = self._fx_invoice(advance_payment=payment_doc)
        else:
            invoice_doc = self._fx_invoice()
            make_payment_reconciliation(payment_doc, invoice_doc, invoice_doc.grand_total)

        self.assertEqual(flt(invoice_doc.base_net_total, 2), 100.0, "invoice net should be 100 INR")
        self.assertEqual(flt(invoice_doc.grand_total, 2), 1.18, "invoice grand total should be 1.18 USD")

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
        self.assertEqual(flt(refs[0].allocated_amount, 2), 1.0, "net allocated should be 1 USD (base 100)")

        # base (INR) ledgers identical to the single-currency matrix, USD accounts aside
        self.assertEqual(self._gl_net_by_account(payment_doc), FX_RECONCILED_GL)

        # the receivable reversal is posted in the account's own currency: 18 INR / 0.18 USD.
        # (filtered by the reversal remark so the separate-account reclass leg on the same
        # receivable/invoice is excluded.)
        reversal = frappe.get_all(
            "GL Entry",
            filters={
                "voucher_no": payment_doc.name,
                "account": USD_DEBTORS,
                "against_voucher": invoice_doc.name,
                "remarks": ["like", "Reversal for GST%"],
                "is_cancelled": 0,
            },
            fields=["credit", "credit_in_account_currency"],
        )
        self.assertEqual(len(reversal), 1)
        self.assertEqual(flt(reversal[0].credit, 2), 18.0, "reversal base credit should be 18 INR")
        self.assertEqual(
            flt(reversal[0].credit_in_account_currency, 2), 0.18, "reversal should be 0.18 in USD"
        )

        # GSTR-1 reports base (INR) taxable values regardless of transaction currency
        self._assert_advance_report(payment_doc, received=500.0, adjusted=-100.0)

        # both documents are at the same rate here, so nothing is left over: the receivable
        # carries exactly the rate it was received at, and no exchange gain/loss arises
        rows = frappe.get_all(
            "GL Entry",
            filters={
                "account": USD_DEBTORS,
                "voucher_no": ["in", (payment_doc.name, invoice_doc.name)],
                "is_cancelled": 0,
            },
            fields=["debit", "credit", "debit_in_account_currency", "credit_in_account_currency"],
        )
        base = flt(sum(row.debit - row.credit for row in rows), 2)
        account_currency = flt(
            sum(row.debit_in_account_currency - row.credit_in_account_currency for row in rows), 2
        )
        self.assertEqual(base, flt(account_currency * FX_RATE, 2))

        # GST Advance Detail declares its amount columns as company currency, so the USD
        # paid / allocated amounts must be converted too, not left sitting beside INR tax
        row = self._advance_detail_summary(payment_doc)
        # inclusive advances are paid gross, so Paid Amount carries the tax; exclusive do not
        self.assertEqual(flt(row["paid_amount"], 2), 590.0 if payment_inclusive else 500.0)
        self.assertEqual(flt(row["gst_paid"], 2), 90.0)
        self.assertEqual(flt(row["allocated_amount"], 2), 100.0)
        self.assertEqual(flt(row["gst_allocated"], 2), 18.0)

    # ---- builders ----

    def _gst_reversal(self, payment_doc, invoice_doc):
        """(company currency, account currency) of the GST reversal against this invoice"""
        rows = frappe.get_all(
            "GL Entry",
            filters={
                "voucher_no": payment_doc.name,
                "account": USD_DEBTORS,
                "against_voucher": invoice_doc.name,
                "remarks": ["like", "Reversal for GST%"],
                "is_cancelled": 0,
            },
            fields=["credit", "credit_in_account_currency"],
        )
        self.assertEqual(len(rows), 1)
        return flt(rows[0].credit, 2), flt(rows[0].credit_in_account_currency, 2)

    def _assert_gst_difference_left_in_receivable(
        self, payment_doc, invoice_doc, expected_base, exchange_gain_loss=10.0
    ):
        """GST is a pass-through: the 18.00 was remitted at the advance's rate, so the slice the
        invoice under-recovers stays collectable in the receivable rather than going to P&L.
        erpnext books the goods portion's difference itself; nothing extra is posted for the tax."""
        # the exchange difference erpnext books lands in its own journal, so the balance has to be
        # read across all three vouchers -- and only those, since the class rolls back once at the end
        vouchers = [
            payment_doc.name,
            invoice_doc.name,
            *frappe.get_all(
                "Journal Entry Account",
                filters={"reference_type": "Payment Entry", "reference_name": payment_doc.name},
                pluck="parent",
            ),
        ]
        rows = frappe.get_all(
            "GL Entry",
            filters={"account": USD_DEBTORS, "voucher_no": ["in", vouchers], "is_cancelled": 0},
            fields=["debit", "credit", "debit_in_account_currency", "credit_in_account_currency"],
        )
        base = flt(sum(row.debit - row.credit for row in rows), 2)
        account_currency = flt(
            sum(row.debit_in_account_currency - row.credit_in_account_currency for row in rows), 2
        )

        self.assertEqual(account_currency, -4.0, "1.18 USD of a 5 USD advance consumed")
        self.assertEqual(base, expected_base)
        self.assertNotEqual(
            base, flt(account_currency * FX_RATE, 2), "the difference is deliberately left here"
        )

        booked = frappe.get_all(
            "GL Entry",
            filters={
                "account": ["like", "Exchange%"],
                "voucher_no": ["in", vouchers],
                "is_cancelled": 0,
            },
            fields=["debit", "credit"],
        )
        self.assertEqual(len(booked), 1, "only erpnext's own, none for the GST slice")
        self.assertEqual(flt(booked[0].credit - booked[0].debit, 2), exchange_gain_loss)

    def _fx_payment(self, inclusive=False):
        # paid 5 USD (inclusive: 5.9 USD) @ FX_RATE -> base 500 + 90 GST INR.
        payment_doc = create_transaction(
            doctype="Payment Entry",
            payment_type="Receive",
            mode_of_payment="Cash",
            company_address="_Test Indian Registered Company-Billing",
            party_type="Customer",
            party=self._usd_customer(),
            customer_address=f"{self._usd_customer()}-Billing",
            paid_from=self._usd_debtors(),  # USD account -> transaction currency USD
            paid_to="Cash - _TIRC",  # INR (company currency)
            paid_amount=5.9 if inclusive else 5,
            is_in_state=1,
            do_not_save=True,
        )
        if inclusive:
            for tax in payment_doc.taxes:
                tax.included_in_paid_amount = 1

        payment_doc.setup_party_account_field()
        payment_doc.set_missing_values()  # fills paid_from_account_currency = USD
        payment_doc.source_exchange_rate = FX_RATE  # set before set_exchange_rate so it is kept
        payment_doc.set_exchange_rate()  # target rate -> 1 (paid_to is INR)
        # base_paid_amount is only computed during validate; derive received (INR) directly
        payment_doc.received_amount = payment_doc.paid_amount * FX_RATE
        payment_doc.save()
        payment_doc.submit()

        return payment_doc

    def _fx_invoice(self, advance_payment=None, conversion_rate=FX_RATE):
        # net 1 USD @ FX_RATE -> base 100 INR + 18% GST, booked on the USD receivable
        invoice_doc = create_transaction(
            doctype="Sales Invoice",
            customer=self._usd_customer(),
            currency="USD",
            conversion_rate=conversion_rate,
            debit_to=self._usd_debtors(),
            is_in_state=1,
            rate=1,
            do_not_save=True,
        )
        invoice_doc.save()

        if advance_payment:
            invoice_doc.set_advances()
            for row in invoice_doc.advances:
                row.allocated_amount = (
                    invoice_doc.net_total if row.reference_name == advance_payment.name else 0
                )

        invoice_doc.submit()

        return invoice_doc

    # ---- fixtures (USD receivable + a USD-currency registered customer) ----

    def _usd_debtors(self):
        return create_account(
            account_name="Debtors USD",
            account_type="Receivable",
            parent_account="Accounts Receivable - _TIRC",
            company="_Test Indian Registered Company",
            account_currency="USD",
        )

    def _usd_customer(self):
        name = "_Test Registered Customer FX"
        if not frappe.db.exists("Customer", name):
            frappe.get_doc(
                {
                    "doctype": "Customer",
                    "customer_name": name,
                    "customer_type": "Company",
                    "gstin": "24AANCA4892J1Z8",
                    "gst_category": "Registered Regular",
                    "default_currency": "USD",
                }
            ).insert()

        address = f"{name}-Billing"
        if not frappe.db.exists("Address", address):
            frappe.get_doc(
                {
                    "doctype": "Address",
                    "address_title": name,
                    "address_type": "Billing",
                    "address_line1": "Test Address - FX",
                    "city": "Test City",
                    "state": "Gujarat",
                    "pincode": "380015",
                    "country": "India",
                    "gstin": "24AANCA4892J1Z8",
                    "gst_category": "Registered Regular",
                    "is_primary_address": 1,
                    "links": [{"link_doctype": "Customer", "link_name": name}],
                }
            ).insert()

        return name
