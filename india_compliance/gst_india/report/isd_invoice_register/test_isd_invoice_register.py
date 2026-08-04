# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase, change_settings
from frappe.utils import add_days, today

from india_compliance.gst_india.doctype.isd_distribution_invoice.test_isd_distribution_invoice import (
    create_distribution_invoice,
    get_auto_recipient_invoice,
    make_isd_pi,
    setup_isd_fixtures,
)
from india_compliance.gst_india.report.isd_invoice_register.isd_invoice_register import execute
from india_compliance.gst_india.utils.isd import sum_row_tax_by_type

COMPANY = "_Test Indian Registered Company"


class TestISDInvoiceRegister(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        setup_isd_fixtures(cls)

    def base_filters(self, **overrides):
        return {
            "company": COMPANY,
            "from_date": add_days(today(), -30),
            "to_date": add_days(today(), 1),
            **overrides,
        }

    def run_report(self, report_view):
        _columns, data = execute(self.base_filters(report_view=report_view))
        return data

    def test_company_is_mandatory(self):
        """Without it the query is unscoped and returns every company's data. `reqd` on the filter
        is client-side only, so the report API must reject it too."""
        for report_view in ("Purchase Invoice", "ISD Distribution Invoice", "ISD Recipient Invoice"):
            with self.subTest(report_view=report_view):
                filters = self.base_filters(report_view=report_view)
                filters.pop("company")

                self.assertRaisesRegex(frappe.ValidationError, "Company is mandatory", execute, filters)

    def test_date_range_is_mandatory(self):
        filters = self.base_filters()
        filters.pop("from_date")
        self.assertRaisesRegex(frappe.ValidationError, "mandatory", execute, filters)

        filters = self.base_filters(from_date=today(), to_date=add_days(today(), -5))
        self.assertRaisesRegex(frappe.ValidationError, "before To Date", execute, filters)

    def test_invalid_recipient_state_is_rejected(self):
        """STATE_NUMBERS.get() would otherwise build the string "None-<state>", which matches
        nothing and reads like missing data rather than a bad filter."""
        filters = self.base_filters(report_view="ISD Distribution Invoice", recipient_state="Not A State")
        self.assertRaisesRegex(frappe.ValidationError, "not a valid State", execute, filters)

    def test_purchase_invoice_view_reports_available_itc(self):
        """One row per (invoice x tax rate), carrying the ITC the ISD has available to distribute."""
        pi = make_isd_pi(self.isd_address.name)

        rows = [row for row in self.run_report("Purchase Invoice") if row.invoice_name == pi.name]

        self.assertEqual(len(rows), 1)
        row = rows[0]
        item = pi.items[0]

        self.assertEqual(row.company_gstin, self.isd_address.gstin)
        self.assertEqual(row.supplier, pi.supplier)
        self.assertEqual(row.pos, pi.place_of_supply)
        self.assertEqual(row.supply_type, "Intra-State")
        self.assertEqual(row.taxable_value, item.net_amount)
        self.assertEqual(row.cgst_amount, item.cgst_amount)
        self.assertEqual(row.sgst_amount, item.sgst_amount)
        self.assertEqual(row.igst_amount, 0)
        self.assertEqual(row.total_invoice_value, pi.base_grand_total)

    def test_distribution_view_reports_available_and_distributed_itc(self):
        pi = make_isd_pi(self.isd_address.name)
        doc = create_distribution_invoice(
            purchase_invoice=pi,
            company_address=self.isd_address.name,
            party_address=self.recipient_address.name,
            branch_turnover=25,
            total_turnover=100,
        )
        source_row = doc.source_items[0]

        rows = [
            row
            for row in self.run_report("ISD Distribution Invoice")
            if row.isd_distribution_invoice == doc.name
        ]

        self.assertEqual(len(rows), 1, "one row per eligibility, and this invoice is all eligible")
        row = rows[0]

        self.assertEqual(row.company_gstin, self.isd_address.gstin)
        self.assertEqual(row.party_gstin, self.recipient_address.gstin)
        self.assertEqual(row.party_pos, doc.party_pos)
        self.assertEqual(row.eligibility, "Eligible")

        # available on the source purchase invoice, before conversion
        self.assertEqual(row.total_cgst, source_row.total_cgst)
        self.assertEqual(row.total_sgst, source_row.total_sgst)
        self.assertEqual(row.total_expense, source_row.total_expense)

        # actually distributed -- a quarter of it, per the turnover ratio
        self.assertEqual(row.distributed_cgst, source_row.distributed_cgst)
        self.assertEqual(row.distributed_sgst, source_row.distributed_sgst)
        self.assertEqual(row.distributed_expense, source_row.distributed_expense)
        self.assertEqual(row.distributed_cgst, row.total_cgst / 4)

    @change_settings("GST Settings", {"auto_create_isd_recipient_invoice": 1})
    def test_recipient_view_reports_received_itc(self):
        pi = make_isd_pi(self.isd_address.name)
        distribution = create_distribution_invoice(
            purchase_invoice=pi,
            company_address=self.isd_address.name,
            party_address=self.recipient_address.name,
            branch_turnover=25,
            total_turnover=100,
        )
        recipient = get_auto_recipient_invoice(distribution)
        source_row = recipient.source_items[0]

        rows = [
            row
            for row in self.run_report("ISD Recipient Invoice")
            if row.isd_recipient_invoice == recipient.name
        ]

        self.assertEqual(len(rows), 1)
        row = rows[0]

        # company / party invert on this side: the branch receives from the ISD
        self.assertEqual(row.company_gstin, self.recipient_address.gstin)
        self.assertEqual(row.party_gstin, self.isd_address.gstin)
        self.assertEqual(row.isd_distribution_invoice_reference, distribution.name)
        self.assertEqual(row.eligibility, "Eligible")

        self.assertEqual(row.recipient_cgst, source_row.distributed_cgst)
        self.assertEqual(row.recipient_sgst, source_row.distributed_sgst)
        self.assertEqual(row.recipient_expense, source_row.distributed_expense)

        # what the branch receives is exactly what the ISD distributed
        self.assertEqual(
            row.recipient_cgst + row.recipient_sgst,
            sum_row_tax_by_type(distribution.source_items[0], "distributed"),
        )
