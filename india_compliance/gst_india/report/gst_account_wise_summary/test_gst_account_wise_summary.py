import frappe
from frappe.tests import IntegrationTestCase, change_settings
from frappe.utils import getdate

from india_compliance.gst_india.doctype.bill_of_entry.bill_of_entry import (
    make_bill_of_entry,
)
from india_compliance.gst_india.report.gst_account_wise_summary.gst_account_wise_summary import (
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
            "voucher_type": "Purchase",
        }
    )


class TestGSTAccountWiseSummary(IntegrationTestCase):
    def setUp(self):
        filters = {"company": COMPANY}
        for doctype in ("Purchase Invoice", "Bill of Entry"):
            frappe.db.delete(doctype, filters=filters)

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_import_of_goods_itc_from_boe(self):
        pi = create_purchase_invoice(supplier="_Test Foreign Supplier", update_stock=1)
        expense_account = pi.items[0].expense_account

        boe = make_bill_of_entry(pi.name)
        boe.items[0].customs_duty = 100
        boe.bill_of_entry_no = "BOE-ACCT-001"
        boe.bill_of_entry_date = getdate()
        boe.save()
        boe.submit()

        _, data = execute(_filters(getdate()))

        row = next(
            (r for r in data if r.get("account_name") == expense_account),
            None,
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["total_amount"], 200.0)
        self.assertEqual(row["total_itc"], 36.0)
        self.assertEqual(row["total_itc_availed"], 36.0)
