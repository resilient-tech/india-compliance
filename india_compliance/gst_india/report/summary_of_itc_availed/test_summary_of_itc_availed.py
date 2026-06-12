import frappe
from frappe.tests import IntegrationTestCase, change_settings
from frappe.utils import getdate

from india_compliance.gst_india.doctype.bill_of_entry.bill_of_entry import (
    make_bill_of_entry,
)
from india_compliance.gst_india.report.summary_of_itc_availed.summary_of_itc_availed import (
    execute,
)
from india_compliance.gst_india.utils.tests import create_purchase_invoice

COMPANY = "_Test Indian Registered Company"
COMPANY_GSTIN = "24AAQCA8719H1ZC"


def _filters(posting_date):
    return frappe._dict(
        {
            "company": COMPANY,
            "company_gstin": COMPANY_GSTIN,
            "date_range": [posting_date, posting_date],
            "filter_by": "Posting Date",
        }
    )


class TestSummaryOfITCAvailed(IntegrationTestCase):
    def setUp(self):
        filters = {"company": COMPANY}
        for doctype in ("Purchase Invoice", "Bill of Entry"):
            frappe.db.delete(doctype, filters=filters)

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_boe_classified_as_import_of_goods(self):
        pi = create_purchase_invoice(supplier="_Test Foreign Supplier", update_stock=1)

        boe = make_bill_of_entry(pi.name)
        boe.items[0].customs_duty = 100
        boe.items[0].gst_hsn_code = "730419"
        boe.bill_of_entry_no = "BOE-ITC-001"
        boe.bill_of_entry_date = getdate()
        boe.save()
        boe.submit()

        _, data = execute(_filters(getdate()))

        import_goods_row = next(
            (
                row
                for row in data
                if row.get("indent") == 0
                and "Import Of Goods (including supplies from SEZ)" in row.get("details", "")
            ),
            None,
        )
        import_services_row = next(
            (
                row
                for row in data
                if row.get("indent") == 0
                and "Import Of Services (excluding inward supplies from SEZ)" in row.get("details", "")
            ),
            None,
        )

        self.assertIsNotNone(import_goods_row)
        self.assertIsNotNone(import_services_row)
        self.assertEqual(import_goods_row["igst_amount"], 36.0)
        self.assertEqual(import_services_row["igst_amount"], 0.0)

    def test_service_purchase_is_grouped_under_input_services(self):
        create_purchase_invoice(
            supplier="_Test Registered Supplier",
            item_code="_Test Service Item",
            is_in_state=True,
        )

        _, data = execute(_filters(getdate()))

        input_services_row = next(
            (
                row
                for row in data
                if row.get("indent") == 1
                and row.get("details") == "Input Services"
                and (row.get("cgst_amount") or 0) > 0
            ),
            None,
        )

        self.assertIsNotNone(input_services_row)
        self.assertEqual(input_services_row["cgst_amount"], 9.0)
        self.assertEqual(input_services_row["sgst_amount"], 9.0)
