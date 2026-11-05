# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase, change_settings

from india_compliance.gst_india.doctype.bill_of_entry.bill_of_entry import (
    make_bill_of_entry,
    make_journal_entry_for_payment,
)
from india_compliance.gst_india.report.bill_of_entry_summary.bill_of_entry_summary import (
    execute,
)
from india_compliance.gst_india.utils.tests import create_purchase_invoice
from india_compliance.tests.erpnext_test_utils import create_account

COMPANY = "_Test Indian Registered Company"
POSTING_DATE = "2023-08-11"


class TestBillOfEntrySummary(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        frappe.new_doc("Fiscal Year").update(
            {
                "year_start_date": "2023-04-01",
                "year_end_date": "2024-03-31",
                "year": "2023-2024",
            }
        ).insert(ignore_if_duplicate=True)

    def setUp(self):
        frappe.db.delete("Bill of Entry", filters={"company": COMPANY})

    def create_bill_of_entry(self, invoice_count=1, charges=None):
        invoices = [
            create_purchase_invoice(
                bill_no=f"BOE-SUMMARY-{index}",
                bill_date=POSTING_DATE,
                posting_date=POSTING_DATE,
                set_posting_time=1,
                qty=10,
                rate=1000,
                supplier="_Test Foreign Supplier",
                supplier_gstin="",
                gst_category="Overseas",
                is_in_state=0,
            )
            for index in range(invoice_count)
        ]

        boe = make_bill_of_entry(invoices[0].name)
        if invoices[1:]:
            boe.get_items_from_purchase_invoice([invoice.name for invoice in invoices[1:]])

        boe.update(
            {
                "bill_of_entry_no": "BOE-SUMMARY",
                "bill_of_entry_date": POSTING_DATE,
                "posting_date": POSTING_DATE,
            }
        )
        for account, amount in (charges or {"Miscellaneous Expenses - _TIRC": 500}).items():
            boe.append("taxes", {"charge_type": "Actual", "account_head": account, "tax_amount": amount})

        boe.save(ignore_permissions=True).submit()

        return boe, invoices

    def run_report(self):
        _columns, data = execute(frappe._dict(company=COMPANY, from_date="2023-08-01", to_date="2023-08-31"))
        return data

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_single_invoice(self):
        boe, invoices = self.create_bill_of_entry()

        data = self.run_report()

        self.assertEqual(len(data), 1)
        row = data[0]
        self.assertEqual(row.name, boe.name)
        self.assertEqual(row.bill_of_entry_no, "BOE-SUMMARY")
        self.assertEqual(row.supplier, invoices[0].supplier)
        self.assertEqual(row.purchase_invoice, invoices[0].name)
        self.assertEqual(row.total_taxes, boe.total_taxes)
        self.assertEqual(row.total_amount_payable, boe.total_amount_payable)
        self.assertEqual(row["Input Tax IGST - _TIRC"], boe.taxes[0].tax_amount)
        self.assertEqual(row["Miscellaneous Expenses - _TIRC"], 500)

        columns, _data = execute(frappe._dict(company=COMPANY, from_date="2023-08-01", to_date="2023-08-31"))
        labels = [column["label"] for column in columns]
        customs_duty_index = labels.index("Total Customs Duty")
        self.assertEqual(
            labels[customs_duty_index + 1 : customs_duty_index + 4],
            ["Input Tax IGST - _TIRC", "Miscellaneous Expenses - _TIRC", "Total Taxes and Charges"],
        )

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_multiple_invoices_stay_one_row(self):
        """GROUP_CONCAT on MariaDB and STRING_AGG on postgres must both list every invoice."""
        boe, invoices = self.create_bill_of_entry(invoice_count=2)

        data = self.run_report()

        self.assertEqual(len(data), 1, "a Bill of Entry must be summarised as exactly one row")
        row = data[0]
        self.assertEqual(row.name, boe.name)
        self.assertEqual(row.supplier, invoices[0].supplier)
        self.assertEqual(
            sorted(row.purchase_invoice.split(",")),
            sorted(invoice.name for invoice in invoices),
        )
        self.assertEqual(row["Miscellaneous Expenses - _TIRC"], 500)

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_similar_account_names_keep_their_own_amounts(self):
        """Both names scrub to late_fee___tirc, so a scrubbed column key would add the amounts together."""
        for account_name in ("Late Fee", "Late-Fee"):
            create_account(
                account_name=account_name,
                parent_account="Indirect Expenses - _TIRC",
                company=COMPANY,
            )

        self.create_bill_of_entry(charges={"Late Fee - _TIRC": 100, "Late-Fee - _TIRC": 50})

        columns, data = execute(frappe._dict(company=COMPANY, from_date="2023-08-01", to_date="2023-08-31"))
        fieldnames = [column["fieldname"] for column in columns]
        self.assertEqual(data[0]["Late Fee - _TIRC"], 100)
        self.assertEqual(data[0]["Late-Fee - _TIRC"], 50)
        self.assertEqual(len(fieldnames), len(set(fieldnames)))

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_payment_journal_entry_is_reported(self):
        boe, _invoices = self.create_bill_of_entry()

        journal_entry = make_journal_entry_for_payment(boe.name)
        journal_entry.cheque_no = "BOE-SUMMARY-PAYMENT"  # mandatory on a Bank Entry
        journal_entry.save().submit()

        data = self.run_report()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0].payment_journal_entry, journal_entry.name)
