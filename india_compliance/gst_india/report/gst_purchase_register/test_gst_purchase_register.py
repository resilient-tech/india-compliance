# Copyright (c) 2024, Resilient Tech and contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase, change_settings
from frappe.utils import getdate

from india_compliance.gst_india.doctype.bill_of_entry.bill_of_entry import (
    make_bill_of_entry,
)
from india_compliance.gst_india.report.gst_purchase_register.gst_purchase_register import (
    execute,
)
from india_compliance.gst_india.utils.tests import create_purchase_invoice

COMPANY = "_Test Indian Registered Company"
COMPANY_GSTIN = "24AAQCA8719H1ZC"


def _filters(posting_date, **kwargs):
    return frappe._dict(
        {
            "company": COMPANY,
            "company_gstin": COMPANY_GSTIN,
            "date_range": [posting_date, posting_date],
            "sub_section": "4",
            "summary_by": "Invoice Wise",
            "invoice_sub_category": None,
            **kwargs,
        }
    )


class TestGSTPurchaseRegister(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.today = getdate()
        cls._create_itc_reversal_42_43()
        cls._create_itc_reversal_others()
        cls._create_itc_reclaim()
        cls._create_sez_service_pi()
        cls._create_overseas_import_service_pi()
        cls._create_boe_import_goods()

    @classmethod
    def _create_itc_reversal_42_43(cls):
        cls.reversal_je = _create_journal_entry(
            cls.today,
            voucher_type="Reversal Of ITC",
            ineligibility_reason="As per rules 42 & 43 of CGST Rules",
            tax_amount=9,
        )

    @classmethod
    def _create_itc_reversal_others(cls):
        cls.reversal_je_others = _create_journal_entry(
            cls.today,
            voucher_type="Reversal Of ITC",
            ineligibility_reason="Others",
            tax_amount=6,
        )

    @classmethod
    def _create_itc_reclaim(cls):
        cls.reclaim_je = _create_journal_entry(
            cls.today,
            voucher_type="Reclaim of ITC Reversal",
            tax_amount=9,
        )

    @classmethod
    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def _create_sez_service_pi(cls):
        pi = create_purchase_invoice(
            supplier="_Test Registered Supplier",
            item_code="_Test Service Item",
            do_not_save=True,
            do_not_submit=True,
        )
        pi.gst_category = "SEZ"
        pi.insert()
        pi.submit()
        cls.sez_service_pi = pi

    @classmethod
    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def _create_overseas_import_service_pi(cls):
        cls.overseas_import_service_pi = create_purchase_invoice(
            supplier="_Test Foreign Supplier",
            item_code="_Test Service Item",
        )

    @classmethod
    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def _create_boe_import_goods(cls):
        boe_pi = create_purchase_invoice(
            supplier="_Test Foreign Supplier",
            update_stock=1,
        )
        cls.boe_pi = boe_pi
        boe = make_bill_of_entry(boe_pi.name)
        boe.items[0].customs_duty = 100
        boe.bill_of_entry_no = "BOE-PR-001"
        boe.bill_of_entry_date = cls.today
        boe.save()
        boe.submit()
        cls.boe = boe

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()

    def test_reversal_of_itc_je_is_in_purchase_register(self):
        _, data = execute(_filters(self.today))

        row = next((r for r in data if r.get("voucher_no") == self.reversal_je.name), None)
        self.assertEqual(row["ineligibility_type"], "Reversal Of ITC")
        self.assertEqual(
            row["invoice_sub_category"],
            "As per rules 42 & 43 of CGST Rules and section 17(5)",
        )
        self.assertEqual(row["cgst_amount"], 9.0)
        self.assertEqual(row["sgst_amount"], 9.0)
        self.assertEqual(row["total_tax"], 18.0)

    def test_reclaim_of_itc_reversal_je_is_in_purchase_register(self):
        _, data = execute(_filters(self.today))

        row = next((r for r in data if r.get("voucher_no") == self.reclaim_je.name), None)
        self.assertEqual(row["ineligibility_type"], "Reclaim of ITC Reversal")
        self.assertEqual(row["invoice_sub_category"], "Reclaim of ITC Reversal")
        self.assertEqual(row["cgst_amount"], 9.0)
        self.assertEqual(row["sgst_amount"], 9.0)
        self.assertEqual(row["total_tax"], 18.0)

    def test_reversal_of_itc_others_je_is_in_purchase_register(self):
        _, data = execute(_filters(self.today))

        row = next(
            (r for r in data if r.get("voucher_no") == self.reversal_je_others.name),
            None,
        )
        self.assertEqual(row["ineligibility_type"], "Reversal Of ITC")
        self.assertEqual(row["invoice_sub_category"], "Others")
        self.assertEqual(row["cgst_amount"], 6.0)
        self.assertEqual(row["sgst_amount"], 6.0)
        self.assertEqual(row["total_tax"], 12.0)

    def test_overview_shows_reversal_and_reclaim_amounts(self):
        _, data = execute(_filters(self.today, summary_by="Overview"))

        by_description = {row["description"]: row for row in data if row.get("indent") == 1}

        reversal_row = by_description.get("As per rules 42 & 43 of CGST Rules and section 17(5)")
        self.assertIsNotNone(reversal_row)
        self.assertEqual(reversal_row["cgst_amount"], 9.0)
        self.assertEqual(reversal_row["sgst_amount"], 9.0)

        others_row = by_description.get("Others")
        self.assertIsNotNone(others_row)
        self.assertEqual(others_row["cgst_amount"], 6.0)
        self.assertEqual(others_row["sgst_amount"], 6.0)

        reclaim_row = by_description.get("Reclaim of ITC Reversal")
        self.assertIsNotNone(reclaim_row)
        self.assertEqual(reclaim_row["cgst_amount"], 9.0)
        self.assertEqual(reclaim_row["sgst_amount"], 9.0)

    def test_boe_in_section_4_as_import_of_goods(self):
        _, data = execute(_filters(self.today, sub_section="4"))

        row = next((r for r in data if r.get("voucher_no") == self.boe.name), None)
        self.assertIsNotNone(row, "BOE should appear in section 4")

        self.assertEqual(row["invoice_sub_category"], "Import Of Goods")
        self.assertEqual(row["igst_amount"], 36.0)

        voucher_nos = [r.get("voucher_no") for r in data]
        self.assertNotIn(
            self.boe_pi.name,
            voucher_nos,
            "Linked purchase invoice should be excluded when BOE exists",
        )

    def test_sez_service_pi_in_section_5(self):
        self.assertEqual(self.sez_service_pi.items[0].gst_treatment, "Nil-Rated")
        _, data = execute(_filters(self.today, sub_section="5"))

        row = next((r for r in data if r.get("voucher_no") == self.sez_service_pi.name), None)
        self.assertIsNotNone(row, "SEZ service PI should appear in section 5")
        self.assertEqual(row["invoice_sub_category"], "Composition Scheme, Exempted, Nil Rated")

    def test_overseas_import_service_pi_in_section_4(self):
        self.assertEqual(self.overseas_import_service_pi.itc_classification, "Import Of Service")
        self.assertEqual(self.overseas_import_service_pi.items[0].gst_treatment, "Taxable")

        _, data = execute(_filters(self.today, sub_section="4"))

        row = next(
            (r for r in data if r.get("voucher_no") == self.overseas_import_service_pi.name),
            None,
        )
        self.assertIsNotNone(row, "Overseas import service PI should appear in section 4")
        self.assertEqual(row["invoice_sub_category"], "Import Of Service")

    def test_overseas_import_service_pi_excluded_from_section_5(self):
        _, data = execute(_filters(self.today, sub_section="5"))
        voucher_nos = [row["voucher_no"] for row in data]

        self.assertNotIn(
            self.overseas_import_service_pi.name,
            voucher_nos,
            "Overseas import service PI should be excluded from section 5",
        )


def _create_journal_entry(posting_date, voucher_type, tax_amount, ineligibility_reason=""):
    if voucher_type == "Reclaim of ITC Reversal":
        accounts = [
            {
                "account": "GST Expense - _TIRC",
                "credit_in_account_currency": tax_amount * 2,
            },
            {
                "account": "Input Tax CGST - _TIRC",
                "debit_in_account_currency": tax_amount,
            },
            {
                "account": "Input Tax SGST - _TIRC",
                "debit_in_account_currency": tax_amount,
            },
        ]
    else:
        accounts = [
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
        ]

    doc = frappe.get_doc(
        {
            "doctype": "Journal Entry",
            "company": COMPANY,
            "company_gstin": COMPANY_GSTIN,
            "posting_date": posting_date,
            "voucher_type": voucher_type,
            "ineligibility_reason": ineligibility_reason,
            "accounts": accounts,
        }
    )
    doc.insert()
    doc.submit()
    return doc
