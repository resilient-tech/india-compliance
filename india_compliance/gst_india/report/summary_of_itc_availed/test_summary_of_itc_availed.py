import frappe
from frappe.tests import IntegrationTestCase, change_settings
from frappe.utils import getdate

from india_compliance.gst_india.doctype.bill_of_entry.bill_of_entry import (
    make_bill_of_entry,
)
from india_compliance.gst_india.doctype.isd_distribution_invoice.test_isd_distribution_invoice import (
    create_recipient_invoice,
    make_isd_pi,
    make_source_item,
    setup_isd_fixtures,
)
from india_compliance.gst_india.report.summary_of_itc_availed.summary_of_itc_availed import (
    execute,
)
from india_compliance.gst_india.utils.tests import create_purchase_invoice

COMPANY = "_Test Indian Registered Company"
COMPANY_GSTIN = "24AAQCA8719H1ZC"
COMPANY_ADDRESS = "_Test Indian Registered Company-Billing"
ITC_FROM_ISD = "Input Tax credit received from ISD"


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
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        setup_isd_fixtures(cls)

    def setUp(self):
        filters = {"company": COMPANY}
        for doctype in ("Purchase Invoice", "Bill of Entry", "ISD Recipient Invoice"):
            frappe.db.delete(doctype, filters=filters)

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

    # ------------------------------------------------------------------ ISD Recipient Invoice
    def create_recipient_invoice(self):
        pi = make_isd_pi(self.isd_address.name)

        return create_recipient_invoice(
            company_address=COMPANY_ADDRESS,
            party_address=self.isd_address.name,
            external_isd_invoice_number=frappe.generate_hash(length=8),
            source_items=make_source_item(pi),
        )

    def test_isd_recipient_invoice_reported_under_itc_from_isd(self):
        source_row = self.create_recipient_invoice().source_items[0]

        _, data = execute(_filters(getdate()))

        # the category has no Inputs / Capital Goods / Input Services breakup, so it is a single
        # row repeated at both indents (get_subcategory returns the category itself)
        isd_row = next(
            row for row in data if row.get("indent") == 0 and ITC_FROM_ISD in row.get("details", "")
        )

        self.assertEqual(isd_row["cgst_amount"], source_row.distributed_cgst)
        self.assertEqual(isd_row["sgst_amount"], source_row.distributed_sgst)
        self.assertEqual(isd_row["igst_amount"], 0.0)

    def test_isd_recipient_invoice_excluded_from_inward_domestic(self):
        """The credit is ISD-classified, so it must not also land in the default domestic bucket."""
        before = self.domestic_total()
        self.create_recipient_invoice()

        self.assertEqual(self.domestic_total(), before)

    def test_isd_registrations_own_purchase_is_not_reported_as_availed(self):
        """The ISD never avails the credit it receives -- it passes it on, and each recipient
        reports its share as ITC from ISD. Counting the ISD's own purchase here as well would
        report the same tax twice on a company-wide run (company_gstin is an optional filter)."""
        before = self.domestic_total()

        pi = make_isd_pi(self.isd_address.name)
        self.assertEqual(pi.is_isd_applicable, 1)

        filters = _filters(getdate())
        filters.pop("company_gstin")
        _, data = execute(filters)

        domestic = sum(
            row.get("cgst_amount") or 0
            for row in data
            if row.get("indent") == 1 and row.get("details") in ("Inputs", "Input Services")
        )
        self.assertEqual(domestic, before)

    def domestic_total(self):
        _, data = execute(_filters(getdate()))

        return sum(
            row.get("cgst_amount") or 0
            for row in data
            if row.get("indent") == 1 and row.get("details") in ("Inputs", "Input Services")
        )
