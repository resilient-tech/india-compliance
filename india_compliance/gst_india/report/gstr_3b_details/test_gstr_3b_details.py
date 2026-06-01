# Copyright (c) 2026, Resilient Tech and contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import get_month, getdate

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

    def get_details(self, section: str):
        today = getdate()
        return run_gstr3b_details(
            {
                "company": "_Test Indian Registered Company",
                "company_gstin": "24AAQCA8719H1ZC",
                "year": today.year,
                "month_or_quarter": get_month(today),
                "section": section,
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
