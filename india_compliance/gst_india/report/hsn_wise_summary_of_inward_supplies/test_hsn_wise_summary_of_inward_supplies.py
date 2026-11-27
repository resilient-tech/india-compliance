import frappe
from frappe.tests import IntegrationTestCase, change_settings
from frappe.utils import today

from india_compliance.gst_india.doctype.bill_of_entry.bill_of_entry import make_bill_of_entry
from india_compliance.gst_india.report.hsn_wise_summary_of_inward_supplies.hsn_wise_summary_of_inward_supplies import (
    execute,
)
from india_compliance.gst_india.utils.tests import append_item, create_purchase_invoice

COMPANY = "_Test Indian Registered Company"


class TestHSNWiseSummaryOfInwardSupplies(IntegrationTestCase):
    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()

    def setUp(self):
        for doctype in ("Purchase Invoice", "Bill of Entry"):
            frappe.db.delete(doctype, filters={"company": COMPANY})

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_ineligible_itc_invoice_counted_once(self):
        """GSTR-9 table 18 overstates inward supplies by every invoice with ineligible ITC."""
        invoice = create_purchase_invoice(
            item_code="_Test Ineligible Service Item",
            supplier_address="_Test Registered Supplier-Billing",
            is_in_state=True,
            do_not_save=1,
        )
        append_item(invoice, frappe._dict(item_code="_Test Trading Goods 1"))
        invoice.submit()

        import_invoice = create_purchase_invoice(supplier="_Test Foreign Supplier", update_stock=1)
        boe = make_bill_of_entry(import_invoice.name)
        boe.items[0].customs_duty = 100
        boe.items[0].is_ineligible_for_itc = 1
        boe.bill_of_entry_no = "123"
        boe.bill_of_entry_date = today()
        boe.submit()

        _, data = execute(
            frappe._dict(
                company=COMPANY,
                company_gstin=invoice.company_gstin,
                from_date=invoice.posting_date,
                to_date=invoice.posting_date,
                filter_by="Posting Date",
            )
        )

        self.assertDictEqual(
            {
                row["hsn_code"]: (
                    row["quantity"],
                    row["total_taxable_value"],
                    row["total_cgst_amount"],
                    row["total_igst_amount"],
                )
                for row in data
            },
            {
                "999900": (1, 100, 9, 0),
                # one from the invoice, one from the bill of entry
                "61149090": (2, 300, 9, 36),
            },
        )
