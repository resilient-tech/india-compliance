# Copyright (c) 2023, Resilient Tech and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from india_compliance.gst_india.doctype.bill_of_entry.bill_of_entry import (
    make_bill_of_entry,
    make_journal_entry_for_payment,
    make_landed_cost_voucher,
)
from india_compliance.gst_india.utils.tests import create_purchase_invoice


class TestBillofEntry(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.db.set_single_value("GST Settings", "enable_overseas_transactions", 1)

    def test_create_bill_of_entry(self):
        pi = create_purchase_invoice(supplier="_Test Foreign Supplier", update_stock=1)

        # Create BOE
        boe = make_bill_of_entry(pi.name)
        boe.items[0].customs_duty = 100
        boe.bill_of_entry_no = "123"
        boe.bill_of_entry_date = today()
        boe.save()
        boe.submit()

        # Verify BOE
        self.assertDocumentEqual(
            {
                "total_customs_duty": 100,
                "total_taxes": 36,  # 18% IGST on (100 + 100)
                "total_amount_payable": 136,
            },
            boe,
        )

        # Verify GL Entries
        gl_entries = frappe.get_all(
            "GL Entry",
            filters={"voucher_type": "Bill of Entry", "voucher_no": boe.name},
            fields=["account", "debit", "credit"],
        )

        for gle in gl_entries:
            if gle.account == boe.customs_expense_account:
                self.assertEqual(gle.debit, boe.total_customs_duty)
            elif "IGST" in gle.account:
                self.assertEqual(gle.debit, boe.total_taxes)
            elif gle.account == boe.customs_payable_account:
                self.assertEqual(gle.credit, boe.total_amount_payable)

        # Create Journal Entry
        je = make_journal_entry_for_payment(boe.name)
        je.cheque_no = "123"
        je.save()
        je.submit()

        self.assertDocumentEqual(
            {
                "account": boe.customs_payable_account,
                "debit": boe.total_amount_payable,
            },
            je.accounts[0],
        )
        self.assertEqual(je.total_debit, boe.total_amount_payable)

        # Create Landed Cost Voucher
        lcv = make_landed_cost_voucher(boe.name)
        lcv.save()
        lcv.submit()

        item = pi.items[0]
        self.assertDocumentEqual(
            {
                "purchase_receipts": [
                    {
                        "receipt_document_type": "Purchase Invoice",
                        "receipt_document": pi.name,
                    }
                ],
                "items": [
                    {
                        "item_code": item.item_code,
                        "purchase_receipt_item": item.name,
                        "applicable_charges": boe.total_customs_duty,
                    }
                ],
                "taxes": [
                    {
                        "expense_account": boe.customs_expense_account,
                        "amount": boe.total_customs_duty,
                    }
                ],
                "distribute_charges_based_on": "Distribute Manually",
            },
            lcv,
        )
