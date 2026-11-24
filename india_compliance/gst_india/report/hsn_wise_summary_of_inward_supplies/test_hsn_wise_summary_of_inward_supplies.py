import frappe
from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.report.hsn_wise_summary_of_inward_supplies.hsn_wise_summary_of_inward_supplies import (
    execute,
)
from india_compliance.gst_india.utils.tests import create_purchase_invoice

COMPANY = "_Test Indian Registered Company"


class TestHSNWiseSummaryOfInwardSupplies(IntegrationTestCase):
    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()

    def setUp(self):
        frappe.db.delete("Purchase Invoice", filters={"company": COMPANY})

    def test_ineligible_itc_invoice_counted_once(self):
        """GSTR-9 table 18 overstates inward supplies by every invoice with ineligible ITC."""
        invoice = create_purchase_invoice(
            item_code="_Test Ineligible Service Item",
            supplier_address="_Test Registered Supplier-Billing",
            is_in_state=True,
        )

        _, data = execute(
            frappe._dict(
                company=COMPANY,
                company_gstin=invoice.company_gstin,
                from_date=invoice.posting_date,
                to_date=invoice.posting_date,
                filter_by="Posting Date",
            )
        )

        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["quantity"], 1)
        self.assertEqual(data[0]["total_taxable_value"], 100)
        self.assertEqual(data[0]["total_cgst_amount"], 9)
