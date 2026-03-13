# Copyright (c) 2024, Resilient Tech and contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate

from india_compliance.gst_india.report.gst_purchase_register.gst_purchase_register import (
    execute,
)

REVERSAL_OF_ITC = "Reversal Of ITC"
RECLAIM_OF_ITC_REVERSAL = "Reclaim of ITC Reversal"


def _filters(posting_date, **kwargs):
    return frappe._dict(
        {
            "company": "_Test Indian Registered Company",
            "company_gstin": "24AAQCA8719H1ZC",
            "date_range": [posting_date, posting_date],
            "sub_section": "4",
            "summary_by": "Invoice Wise",
            "invoice_sub_category": None,
            **kwargs,
        }
    )


class TestGSTPurchaseRegisterITCJournalEntries(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.today = getdate()
        cls.reversal_je = create_itc_reversal_journal_entry(cls.today)
        cls.reversal_je_others = create_itc_reversal_journal_entry(
            cls.today,
            ineligibility_reason="Others",
            tax_amount=6,
        )
        cls.reclaim_je = create_itc_reclaim_journal_entry(cls.today)

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()

    def test_reversal_of_itc_je_is_in_purchase_register(self):
        self.assertEqual(
            frappe.db.get_value("Journal Entry", self.reversal_je.name, "voucher_type"),
            REVERSAL_OF_ITC,
        )

        _, data = execute(_filters(self.today))

        reversal_rows = [
            row for row in data if row.get("voucher_no") == self.reversal_je.name
        ]

        row = reversal_rows[0]
        self.assertEqual(row["ineligibility_type"], REVERSAL_OF_ITC)
        self.assertEqual(
            row["invoice_sub_category"],
            "As per rules 42 & 43 of CGST Rules and section 17(5)",
        )
        self.assertEqual(row["cgst_amount"], 9.0)
        self.assertEqual(row["sgst_amount"], 9.0)
        self.assertEqual(row["total_tax"], 18.0)

    def test_reclaim_of_itc_reversal_je_is_in_purchase_register(self):
        self.assertEqual(
            frappe.db.get_value("Journal Entry", self.reclaim_je.name, "voucher_type"),
            RECLAIM_OF_ITC_REVERSAL,
        )

        _, data = execute(_filters(self.today))

        reclaim_rows = [
            row for row in data if row.get("voucher_no") == self.reclaim_je.name
        ]

        row = reclaim_rows[0]
        self.assertEqual(row["ineligibility_type"], RECLAIM_OF_ITC_REVERSAL)
        self.assertEqual(row["invoice_sub_category"], RECLAIM_OF_ITC_REVERSAL)
        self.assertEqual(row["cgst_amount"], 9.0)
        self.assertEqual(row["sgst_amount"], 9.0)
        self.assertEqual(row["total_tax"], 18.0)

    def test_reversal_of_itc_others_je_is_in_purchase_register(self):
        self.assertEqual(
            frappe.db.get_value(
                "Journal Entry", self.reversal_je_others.name, "voucher_type"
            ),
            REVERSAL_OF_ITC,
        )

        _, data = execute(_filters(self.today))

        reversal_rows = [
            row for row in data if row.get("voucher_no") == self.reversal_je_others.name
        ]

        row = reversal_rows[0]
        self.assertEqual(row["ineligibility_type"], REVERSAL_OF_ITC)
        self.assertEqual(row["invoice_sub_category"], "Others")
        self.assertEqual(row["cgst_amount"], 6.0)
        self.assertEqual(row["sgst_amount"], 6.0)
        self.assertEqual(row["total_tax"], 12.0)

    def test_overview_shows_reversal_and_reclaim_amounts(self):
        _, data = execute(_filters(self.today, summary_by="Overview"))

        by_description = {
            row["description"]: row for row in data if row.get("indent") == 1
        }

        reversal_row = by_description.get(
            "As per rules 42 & 43 of CGST Rules and section 17(5)"
        )
        self.assertIsNotNone(reversal_row)
        self.assertEqual(reversal_row["cgst_amount"], 9.0)
        self.assertEqual(reversal_row["sgst_amount"], 9.0)

        others_row = by_description.get("Others")
        self.assertIsNotNone(others_row)
        self.assertEqual(others_row["cgst_amount"], 6.0)
        self.assertEqual(others_row["sgst_amount"], 6.0)

        reclaim_row = by_description.get(RECLAIM_OF_ITC_REVERSAL)
        self.assertIsNotNone(reclaim_row)
        self.assertEqual(reclaim_row["cgst_amount"], 9.0)
        self.assertEqual(reclaim_row["sgst_amount"], 9.0)


def create_itc_reversal_journal_entry(
    posting_date,
    ineligibility_reason="As per rules 42 & 43 of CGST Rules",
    tax_amount=9,
):
    journal_entry = frappe.get_doc(
        {
            "doctype": "Journal Entry",
            "company": "_Test Indian Registered Company",
            "company_gstin": "24AAQCA8719H1ZC",
            "posting_date": posting_date,
            "voucher_type": REVERSAL_OF_ITC,
            "ineligibility_reason": ineligibility_reason,
            "accounts": [
                {
                    "account": "GST Expense - _TIRC",
                    "debit_in_account_currency": tax_amount * 2,
                },
                {
                    "account": "Input Tax CGST - _TIRC",
                    "credit_in_account_currency": tax_amount,
                },
                {
                    "account": "Input Tax SGST - _TIRC",
                    "credit_in_account_currency": tax_amount,
                },
            ],
        }
    )
    journal_entry.insert()
    journal_entry.submit()
    return journal_entry


def create_itc_reclaim_journal_entry(posting_date):
    journal_entry = frappe.get_doc(
        {
            "doctype": "Journal Entry",
            "company": "_Test Indian Registered Company",
            "company_gstin": "24AAQCA8719H1ZC",
            "posting_date": posting_date,
            "voucher_type": RECLAIM_OF_ITC_REVERSAL,
            "accounts": [
                {"account": "GST Expense - _TIRC", "credit_in_account_currency": 18},
                {"account": "Input Tax CGST - _TIRC", "debit_in_account_currency": 9},
                {"account": "Input Tax SGST - _TIRC", "debit_in_account_currency": 9},
            ],
        }
    )
    journal_entry.insert()
    journal_entry.submit()
    return journal_entry
