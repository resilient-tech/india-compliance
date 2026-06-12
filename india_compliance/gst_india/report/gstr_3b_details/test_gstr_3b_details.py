# Copyright (c) 2026, Resilient Tech and contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import get_first_day, get_last_day, get_month, getdate

from india_compliance.gst_india.report.gst_purchase_register.gst_purchase_register import (
    execute as run_purchase_register,
)
from india_compliance.gst_india.report.gstr_3b_details.gstr_3b_details import (
    execute as run_gstr3b_details,
)
from india_compliance.gst_india.utils.tests import (
    create_itc_reclaim_journal_entry,
    create_purchase_invoice,
)


class TestGSTR3BDetails(IntegrationTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        filters = {"company": "_Test Indian Registered Company"}

        for doctype in (
            "Purchase Invoice",
            "Journal Entry",
            "Bill of Entry",
        ):
            frappe.db.delete(doctype, filters=filters)

        frappe.db.set_single_value("GST Settings", "enable_overseas_transactions", 1)

    def get_details(self, sub_section: str, invoice_sub_category=None):
        today = getdate()
        return run_gstr3b_details(
            {
                "company": "_Test Indian Registered Company",
                "company_gstin": "24AAQCA8719H1ZC",
                "year": today.year,
                "month_or_quarter": get_month(today),
                "sub_section": sub_section,
                "invoice_sub_category": invoice_sub_category,
            }
        )

    def test_inward_nil_non_gst_report_includes_sez_services(self):
        pi = create_purchase_invoice(
            supplier="_Test Registered Supplier",
            do_not_save=1,
            do_not_submit=1,
            item_code="_Test Service Item",
        )
        pi.gst_category = "SEZ"
        pi.insert()
        pi.submit()

        _, rows = self.get_details("5")

        self.assertIn(pi.name, [row["voucher_no"] for row in rows])

    def test_inward_nil_non_gst_report_excludes_overseas_import_services(self):
        pi = create_purchase_invoice(
            supplier="_Test Foreign Supplier",
            do_not_save=1,
            do_not_submit=1,
            item_code="_Test Service Item",
        )
        pi.insert()
        pi.submit()

        self.assertEqual(pi.itc_classification, "Import Of Service")

        _, rows = self.get_details("5")

        self.assertNotIn(pi.name, [row["voucher_no"] for row in rows])

    def test_itc_details_report_includes_itc_reclaim_entries(self):
        journal_entry = create_itc_reclaim_journal_entry(posting_date=getdate(), tax_amount=9)

        _, data = self.get_details("4")
        row = next((item for item in data if item["voucher_no"] == journal_entry.name), None)

        self.assertIsNotNone(row)
        self.assertEqual(row["invoice_sub_category"], "Reclaim of ITC Reversal")
        self.assertEqual(row["cgst_amount"], 9.0)
        self.assertEqual(row["sgst_amount"], 9.0)

    def test_itc_details_report_includes_pos_restricted_itc(self):
        purchase_invoice = create_purchase_invoice(
            posting_date=getdate(),
            update_stock=1,
            place_of_supply="27-Maharashtra",
            is_out_state=1,
            supplier_address="_Test Registered Supplier-Billing",
        )
        self.assertEqual(purchase_invoice.ineligibility_reason, "ITC restricted due to PoS rules")

        _, data = self.get_details("4")
        row = next((item for item in data if item["voucher_no"] == purchase_invoice.name), None)

        self.assertIsNotNone(row)
        self.assertEqual(row["invoice_sub_category"], "ITC restricted due to PoS rules")
        self.assertGreater(row["igst_amount"], 0)

    def create_section_4_documents(self):
        # PoS-restricted Purchase Invoice ("ITC restricted due to PoS rules")
        create_purchase_invoice(
            posting_date=getdate(),
            update_stock=1,
            place_of_supply="27-Maharashtra",
            is_out_state=1,
            supplier_address="_Test Registered Supplier-Billing",
        )
        # ITC Reclaim Journal Entry ("Reclaim of ITC Reversal")
        create_itc_reclaim_journal_entry(posting_date=getdate(), tax_amount=9)

    def test_invoice_sub_category_filter_narrows_rows(self):
        self.create_section_4_documents()

        _, all_rows = self.get_details("4")
        _, reclaim_rows = self.get_details("4", invoice_sub_category=["Reclaim of ITC Reversal"])

        self.assertTrue(len(reclaim_rows) < len(all_rows))
        self.assertTrue(all(row["invoice_sub_category"] == "Reclaim of ITC Reversal" for row in reclaim_rows))

    def test_details_totals_match_purchase_register(self):
        # A mix of inward documents across Section-4 sub-categories.
        self.create_section_4_documents()

        _, details_rows = self.get_details("4")
        _, register_rows = self.get_purchase_register("4")

        amount_fields = ("igst_amount", "cgst_amount", "sgst_amount", "cess_amount")
        for field in amount_fields:
            self.assertEqual(
                sum(row.get(field, 0) or 0 for row in details_rows),
                sum(row.get(field, 0) or 0 for row in register_rows),
                msg=f"{field} total differs between GSTR-3B Details and GST Purchase Register",
            )

    def get_purchase_register(self, sub_section: str):
        today = getdate()
        return run_purchase_register(
            frappe._dict(
                {
                    "company": "_Test Indian Registered Company",
                    "company_gstin": "24AAQCA8719H1ZC",
                    "date_range": [get_first_day(today), get_last_day(today)],
                    "filter_by": "ITC Claim Period",
                    "summary_by": "Summary by Invoice",
                    "sub_section": sub_section,
                }
            )
        )
