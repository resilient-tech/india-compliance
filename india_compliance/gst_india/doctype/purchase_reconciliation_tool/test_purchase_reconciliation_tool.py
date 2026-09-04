# Copyright (c) 2022, Resilient Tech and Contributors
# See license.txt

import datetime
import json

import frappe
from frappe.tests import IntegrationTestCase, change_settings
from frappe.tests.utils import make_test_objects
from frappe.utils import getdate

from india_compliance.gst_india.doctype.bill_of_entry.bill_of_entry import (
    make_bill_of_entry,
)
from india_compliance.gst_india.utils.itc_claim import (
    ITC_CLAIM_PERIOD_DEFERRED,
    format_period,
    update_gstr3b_filing_status,
)
from india_compliance.gst_india.utils.tests import (
    create_purchase_invoice as _create_purchase_invoice,
)

IGNORE_TEST_RECORD_DEPENDENCIES = ["Company"]

PURCHASE_INVOICE_DEFAULT_ARGS = {
    "bill_no": "BILL-23-00001",
    "bill_date": "2023-12-11",
    "qty": 10,
    "rate": 1000,
    "is_in_state": 1,
    "posting_date": "2023-12-11",
    "set_posting_time": 1,
}
INWARD_SUPPLY_DEFAULT_ARGS = {
    "company": "_Test Indian Registered Company",
    "company_gstin": "24AAQCA8719H1ZC",
    "supplier_name": "_Test Registered Supplier",
    "bill_no": "BILL-23-00001",
    "bill_date": "2023-12-11",
    "classification": "B2B",
    "doc_type": "Invoice",
    "supply_type": "Regular",
    "place_of_supply": "24-Gujarat",
    "supplier_gstin": "24AABCR6898M1ZN",
    "items": [{"taxable_value": 10000, "rate": 18, "sgst": 900, "cgst": 900}],
    "document_value": 11800,
    "itc_availability": "Yes",
    "return_period_2b": "122023",
    "gen_date_2b": "2023-12-11",
}
BILL_OF_ENTRY_DEFAULT_ARGS = {
    "supplier": "_Test Foreign Supplier",
    "supplier_gstin": "",
    "gst_category": "Overseas",
    "is_in_state": 0,
    "posting_date": "2023-12-11",
    "set_posting_time": 1,
}


class TestPurchaseReconciliationTool(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # create 2023-2024 fiscal year
        fiscal_year = frappe.new_doc("Fiscal Year")
        fiscal_year.update(
            {
                "year_start_date": "2023-04-01",
                "year_end_date": "2024-03-31",
                "year": "2023-2024",
            }
        ).insert(ignore_if_duplicate=True)

        cls.test_data = frappe.get_file_json(
            frappe.get_app_path(
                "india_compliance",
                "gst_india",
                "data",
                "test_purchase_reconciliation_tool.json",
            )
        )

        cls.create_test_data()

    def test_purchase_reconciliation_tool(self):
        purchase_reconciliation_tool = frappe.get_doc("Purchase Reconciliation Tool")
        purchase_reconciliation_tool.update(
            {
                # Reconcile all companies
                "company_gstin": "All",
                "period": "Custom",
                "from_date": "2023-11-01",
                "to_date": "2023-12-31",
                "gst_return": "GSTR 2B",
            }
        )

        reconciled_data = purchase_reconciliation_tool.reconcile_and_generate_data()

        for row in reconciled_data:
            for key, value in row.items():
                if isinstance(value, datetime.date):
                    row[key] = str(value)

        for row in reconciled_data:
            self.assertDictEqual(
                row,
                self.reconciled_data.get((row.purchase_invoice_name, row.inward_supply_name)) or {},
            )

    @classmethod
    def create_test_data(cls):
        frappe.db.set_single_value("GST Settings", "enable_overseas_transactions", 1)
        test_cases = cls.test_data.get("TEST_CASES")

        make_test_objects("Address", cls.test_data.get("ADDRESSES"), reset=True)

        cls.reconciled_data = frappe._dict()

        for test_case in test_cases.values():
            for value in test_case:
                if value.get("PURCHASE_INVOICE"):
                    pi = create_purchase_invoice(**value.get("PURCHASE_INVOICE"))

                elif value.get("BILL_OF_ENTRY"):
                    pi = create_boe(**value.get("BILL_OF_ENTRY"))

                if value.get("INWARD_SUPPLY"):
                    gst_is = create_gst_inward_supply(**value.get("INWARD_SUPPLY"))

                _reconciled_data = value.get("RECONCILED_DATA")

                _reconciled_data["purchase_invoice_name"] = pi.get("name")
                _reconciled_data["inward_supply_name"] = gst_is.get("name")

                cls.reconciled_data[(pi.get("name"), gst_is.get("name"))] = _reconciled_data

        frappe.db.set_single_value("GST Settings", "enable_overseas_transactions", 0)

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_bill_of_entry_over_multiple_invoices_is_one_row(self):
        dates = {"bill_date": "2023-08-11", "posting_date": "2023-08-11"}

        # no GST taxes on the invoice: that is what makes an import BoE-applicable
        invoices = [
            create_purchase_invoice(
                bill_no=f"BOE-MULTI-{index}",
                supplier="_Test Foreign Supplier",
                supplier_gstin="",
                gst_category="Overseas",
                is_in_state=0,
                **dates,
            )
            for index in (1, 2)
        ]

        boe = make_bill_of_entry(invoices[0].name)
        boe.get_items_from_purchase_invoice([invoices[1].name])
        boe.update(
            {
                "bill_of_entry_no": "BOE-MULTI-PI",
                "bill_of_entry_date": dates["bill_date"],
                "posting_date": dates["posting_date"],
            }
        )
        boe.save(ignore_permissions=True).submit()

        # the BoE really does span both invoices, else the test proves nothing
        self.assertEqual(
            {item.purchase_invoice for item in boe.items},
            {invoice.name for invoice in invoices},
        )

        tool = frappe.get_doc("Purchase Reconciliation Tool")
        tool.update(
            {
                "company": "_Test Indian Registered Company",
                "company_gstin": "24AAQCA8719H1ZC",
                "period": "Custom",
                "from_date": "2023-08-01",
                "to_date": "2023-08-31",
                "gst_return": "GSTR 2B",
            }
        )
        rows = [row for row in tool.reconcile_and_generate_data() if row.purchase_invoice_name == boe.name]

        self.assertEqual(len(rows), 1, "a Bill of Entry must reconcile as exactly one row")
        row = rows[0]

        self.assertEqual(row.purchase_doctype, "Bill of Entry")
        self.assertEqual(row.supplier, invoices[0].supplier)
        self.assertEqual(row.supplier_name, invoices[0].supplier_name)
        self.assertEqual(row.bill_no, boe.bill_of_entry_no)
        self.assertEqual(row.classification, "IMPG")
        self.assertEqual(row.match_status, "Only in Books")

        # nothing to reconcile against, so the differences are the BoE's own totals, summed
        # over every item of both invoices rather than taken from one of them
        self.assertEqual(row.taxable_value_difference, -boe.total_taxable_value)
        self.assertEqual(row.tax_difference, -sum(item.igst_amount for item in boe.items))

        # the detail view keeps the BoE doc, so the per-invoice fields can be checked directly
        purchase = tool.get_invoice_details(boe.name, None)._purchase_invoice
        self.assertEqual(purchase.taxable_value, boe.total_taxable_value)
        self.assertEqual(purchase.igst, sum(item.igst_amount for item in boe.items))

        # reported for SEZ invoices only, so an overseas import carries none of them
        self.assertIsNone(purchase.supplier_gstin)
        self.assertIsNone(purchase.gst_category)
        self.assertIsNone(purchase.place_of_supply)

    @change_settings("Buying Settings", {"supp_master_name": "Naming Series"})
    def test_supplier_name_of_unbooked_invoice_is_the_supplier_title(self):
        """
        A row with no Purchase Invoice takes its supplier name from the GSTIN.
        That must be the supplier's name, as on every other row, not its docname.
        """
        supplier = frappe.get_doc(
            {
                "doctype": "Supplier",
                "supplier_name": "_Test Series Named Supplier",
                "supplier_type": "Company",
                "gstin": "24AANFA2641L1ZF",
                "gst_category": "Registered Regular",
            }
        ).insert()

        # else the test proves nothing: the docname must differ from the supplier name
        self.assertNotEqual(supplier.name, supplier.supplier_name)

        # 2A/2B need not report the supplier's name, which is what makes the guess necessary
        gst_is = create_gst_inward_supply(
            supplier_name="",
            supplier_gstin=supplier.gstin,
            bill_no="RECO-NAME-001",
            bill_date="2024-02-10",
            return_period_2b="022024",
            gen_date_2b="2024-02-14",
        )

        prt = frappe.get_doc("Purchase Reconciliation Tool")
        prt.update(
            {
                "company_gstin": "24AAQCA8719H1ZC",
                "period": "Custom",
                "from_date": "2024-02-01",
                "to_date": "2024-02-29",
                "gst_return": "GSTR 2B",
            }
        )
        rows = [row for row in prt.reconcile_and_generate_data() if row.inward_supply_name == gst_is.name]

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].match_status, "Only in 2A/2B")
        self.assertEqual(rows[0].supplier, supplier.name)
        self.assertEqual(rows[0].supplier_name, supplier.supplier_name)

    def test_itc_claim_period_on_reconciliation_match(self):
        """
        Test ITC Claim Period is updated when a Purchase Invoice is matched
        with a GST Inward Supply during reconciliation.
        """
        pinv = create_purchase_invoice(
            bill_no="ITC-REC-003",
            bill_date="2023-09-15",
            posting_date="2023-09-15",
        )

        gst_is = create_gst_inward_supply(
            bill_no="ITC-REC-003",
            bill_date="2023-09-15",
            return_period_2b="012024",
        )

        prt = frappe.get_doc("Purchase Reconciliation Tool")
        prt.update(
            {
                "company_gstin": "24AAQCA8719H1ZC",
                "period": "Custom",
                "from_date": "2023-09-01",
                "to_date": "2024-01-31",
                "gst_return": "GSTR 2B",
            }
        )
        prt.reconcile_and_generate_data()

        itc_claim_period = frappe.db.get_value("Purchase Invoice", pinv.name, "itc_claim_period")
        self.assertEqual(itc_claim_period, gst_is.return_period_2b)

    def test_itc_claim_period_deferred_on_rejected_ims(self):
        """
        Test ITC Claim Period is set to 'Deferred' when matched inward supply
        has ims_action='Rejected'.
        """
        pinv = create_purchase_invoice(
            bill_no="ITC-REC-004",
            bill_date="2023-10-15",
            posting_date="2023-10-15",
        )

        gst_is = create_gst_inward_supply(
            bill_no="ITC-REC-004",
            bill_date="2023-10-15",
            return_period_2b="102023",
        )
        frappe.db.set_value("GST Inward Supply", gst_is.name, "ims_action", "Rejected")

        prt = frappe.get_doc("Purchase Reconciliation Tool")
        prt.update(
            {
                "company_gstin": "24AAQCA8719H1ZC",
                "period": "Custom",
                "from_date": "2023-10-01",
                "to_date": "2023-10-31",
                "gst_return": "GSTR 2B",
            }
        )
        prt.reconcile_and_generate_data()

        itc_claim_period = frappe.db.get_value("Purchase Invoice", pinv.name, "itc_claim_period")
        self.assertEqual(itc_claim_period, ITC_CLAIM_PERIOD_DEFERRED)

    def test_itc_claim_period_posting_period_when_2b_earlier(self):
        """
        When 2B return_period < posting_period, ITC Claim Period
        should use the posting period (the later one).
        """
        pinv = create_purchase_invoice(
            bill_no="ITC-REC-005",
            bill_date="2024-01-10",
            posting_date="2024-01-10",
        )

        create_gst_inward_supply(
            bill_no="ITC-REC-005",
            bill_date="2024-01-10",
            return_period_2b="102023",  # Earlier than posting (012024)
        )

        prt = frappe.get_doc("Purchase Reconciliation Tool")
        prt.update(
            {
                "company_gstin": "24AAQCA8719H1ZC",
                "period": "Custom",
                "from_date": "2023-10-01",
                "to_date": "2024-01-31",
                "gst_return": "GSTR 2B",
            }
        )
        prt.reconcile_and_generate_data()

        itc_claim_period = frappe.db.get_value("Purchase Invoice", pinv.name, "itc_claim_period")
        # posting period (012024) > 2B period (102023), so posting
        self.assertEqual(itc_claim_period, format_period(pinv.posting_date))

    def test_itc_claim_period_deferred_on_pending_ims(self):
        """
        ITC Claim Period is set to 'Deferred' when matched inward supply
        has ims_action='Pending'.
        """
        pinv = create_purchase_invoice(
            bill_no="ITC-REC-006",
            bill_date="2023-10-15",
            posting_date="2023-10-15",
        )

        gst_is = create_gst_inward_supply(
            bill_no="ITC-REC-006",
            bill_date="2023-10-15",
            return_period_2b="102023",
        )
        frappe.db.set_value("GST Inward Supply", gst_is.name, "ims_action", "Pending")

        prt = frappe.get_doc("Purchase Reconciliation Tool")
        prt.update(
            {
                "company_gstin": "24AAQCA8719H1ZC",
                "period": "Custom",
                "from_date": "2023-10-01",
                "to_date": "2023-10-31",
                "gst_return": "GSTR 2B",
            }
        )
        prt.reconcile_and_generate_data()

        itc_claim_period = frappe.db.get_value("Purchase Invoice", pinv.name, "itc_claim_period")
        self.assertEqual(itc_claim_period, ITC_CLAIM_PERIOD_DEFERRED)

    def test_itc_claim_period_no_change_when_filed(self):
        """
        Reconciliation should NOT update ITC Claim Period if the
        current period is already filed.
        """
        pinv = create_purchase_invoice(
            bill_no="ITC-REC-007",
            bill_date="2023-08-15",
            posting_date="2023-08-15",
        )

        current_period = frappe.db.get_value("Purchase Invoice", pinv.name, "itc_claim_period")
        self.assertEqual(current_period, "082023")

        # File 082023
        update_gstr3b_filing_status(
            company_gstin="24AAQCA8719H1ZC",
            month_or_quarter="August",
            year=2023,
            status="Filed",
        )

        create_gst_inward_supply(
            bill_no="ITC-REC-007",
            bill_date="2023-08-15",
            return_period_2b="092023",  # Different period
        )

        prt = frappe.get_doc("Purchase Reconciliation Tool")
        prt.update(
            {
                "company_gstin": "24AAQCA8719H1ZC",
                "period": "Custom",
                "from_date": "2023-08-01",
                "to_date": "2023-09-30",
                "gst_return": "GSTR 2B",
            }
        )
        prt.reconcile_and_generate_data()

        # Period should remain unchanged (filed)
        itc_claim_period = frappe.db.get_value("Purchase Invoice", pinv.name, "itc_claim_period")
        self.assertEqual(itc_claim_period, "082023")

        # cleanup
        update_gstr3b_filing_status(
            company_gstin="24AAQCA8719H1ZC",
            month_or_quarter="August",
            year=2023,
            status="Not Filed",
        )

    def test_get_invoice_details_with_none_inward_supply_name(self):
        """
        get_invoice_details with inward_supply_name=None must not raise FrappeTypeError.
        """
        pinv = create_purchase_invoice(
            bill_no="GID-001",
            bill_date="2024-01-01",
            posting_date="2024-01-01",
        )

        prt = frappe.get_doc("Purchase Reconciliation Tool")
        prt.update(
            {
                "company_gstin": "24AAQCA8719H1ZC",
                "period": "Custom",
                "from_date": "2024-01-01",
                "to_date": "2024-01-31",
                "gst_return": "GSTR 2B",
            }
        )
        prt.reconcile_and_generate_data()

        result = prt.get_invoice_details(
            purchase_name=pinv.name,
            inward_supply_name=None,
        )

        self.assertEqual(result.purchase_invoice_name, pinv.name)
        self.assertEqual(result.match_status, "Only in Books")
        self.assertIsNone(result.inward_supply_name)

    def test_get_invoice_details_with_none_purchase_name(self):
        """
        get_invoice_details with purchase_name=None must not raise FrappeTypeError.
        """
        gst_is = create_gst_inward_supply(
            bill_no="GID-002",
            bill_date="2024-01-01",
            return_period_2b="012024",
        )

        prt = frappe.get_doc("Purchase Reconciliation Tool")
        prt.update(
            {
                "company_gstin": "24AAQCA8719H1ZC",
                "period": "Custom",
                "from_date": "2024-01-01",
                "to_date": "2024-01-31",
                "gst_return": "GSTR 2B",
            }
        )
        prt.reconcile_and_generate_data()

        result = prt.get_invoice_details(
            purchase_name=None,
            inward_supply_name=gst_is.name,
        )

        self.assertEqual(result.inward_supply_name, gst_is.name)
        self.assertEqual(result.match_status, "Only in 2A/2B")
        self.assertIsNone(result.purchase_invoice_name)
        self.assertEqual(result._inward_supply.doc_type, "Invoice")

    def test_link_documents_with_none_inward_supply_name(self):
        """
        link_documents with inward_supply_name=None must not raise FrappeTypeError.
        """
        pinv = create_purchase_invoice(
            bill_no="GID-003",
            bill_date="2024-01-01",
            posting_date="2024-01-01",
        )

        prt = frappe.get_doc("Purchase Reconciliation Tool")
        prt.update(
            {
                "company_gstin": "24AAQCA8719H1ZC",
                "period": "Custom",
                "from_date": "2024-01-01",
                "to_date": "2024-01-31",
                "gst_return": "GSTR 2B",
            }
        )
        prt.reconcile_and_generate_data()
        result = prt.link_documents(
            purchase_invoice_name=pinv.name,
            inward_supply_name=None,
            link_doctype="Purchase Invoice",
        )
        self.assertIsInstance(result, list)

    def test_link_documents_with_none_purchase_invoice_name(self):
        """
        link_documents with purchase_invoice_name=None must not raise FrappeTypeError.
        """
        gst_is = create_gst_inward_supply(
            bill_no="GID-004",
            bill_date="2024-01-01",
            return_period_2b="012024",
        )

        prt = frappe.get_doc("Purchase Reconciliation Tool")
        prt.update(
            {
                "company_gstin": "24AAQCA8719H1ZC",
                "period": "Custom",
                "from_date": "2024-01-01",
                "to_date": "2024-01-31",
                "gst_return": "GSTR 2B",
            }
        )
        prt.reconcile_and_generate_data()
        result = prt.link_documents(
            purchase_invoice_name=None,
            inward_supply_name=gst_is.name,
            link_doctype="Purchase Invoice",
        )
        self.assertIsInstance(result, list)

    def test_link_documents_with_none_link_doctype(self):
        """
        link_documents with link_doctype=None must be a no-op.
        """
        pinv = create_purchase_invoice(
            bill_no="GID-005",
            bill_date="2024-01-01",
            posting_date="2024-01-01",
        )
        gst_is = create_gst_inward_supply(
            bill_no="GID-005",
            bill_date="2024-01-01",
            return_period_2b="012024",
        )

        prt = frappe.get_doc("Purchase Reconciliation Tool")
        prt.update(
            {
                "company_gstin": "24AAQCA8719H1ZC",
                "period": "Custom",
                "from_date": "2024-01-01",
                "to_date": "2024-01-31",
                "gst_return": "GSTR 2B",
            }
        )
        prt.reconcile_and_generate_data()
        result = prt.link_documents(
            purchase_invoice_name=pinv.name,
            inward_supply_name=gst_is.name,
            link_doctype=None,
        )
        self.assertIsInstance(result, list)

    def test_unlink_documents_skips_rows_with_nothing_to_unlink(self):
        """
        A batch with unlinked rows must still unlink the linked ones and return both sides.
        """
        pinv = create_purchase_invoice(
            bill_no="GID-006",
            bill_date="2024-01-01",
            posting_date="2024-01-01",
        )
        gst_is = create_gst_inward_supply(
            bill_no="GID-006",
            bill_date="2024-01-01",
            return_period_2b="012024",
        )

        prt = frappe.get_doc("Purchase Reconciliation Tool")
        prt.update(
            {
                "company_gstin": "24AAQCA8719H1ZC",
                "period": "Custom",
                "from_date": "2024-01-01",
                "to_date": "2024-01-31",
                "gst_return": "GSTR 2B",
            }
        )
        prt.reconcile_and_generate_data()
        self.assertEqual(frappe.db.get_value("GST Inward Supply", gst_is.name, "link_name"), pinv.name)

        result = prt.unlink_documents(
            [
                {
                    "purchase_invoice_name": pinv.name,
                    "inward_supply_name": gst_is.name,
                    "purchase_doctype": "Purchase Invoice",
                },
                # nothing to unlink, must be skipped
                {
                    "purchase_invoice_name": "",
                    "inward_supply_name": gst_is.name,
                    "purchase_doctype": "Purchase Invoice",
                },
            ]
        )

        self.assertFalse(frappe.db.get_value("GST Inward Supply", gst_is.name, "link_name"))
        self.assertEqual(
            frappe.db.get_value("Purchase Invoice", pinv.name, "reconciliation_status"),
            "Unreconciled",
        )

        # both sides come back so the list can be refreshed
        names = {row.purchase_invoice_name for row in result} | {row.inward_supply_name for row in result}
        self.assertIn(pinv.name, names)
        self.assertIn(gst_is.name, names)

    def test_sync_details_for_purchase_invoice(self):
        """
        Bill no / date reported in 2A/2B are copied onto the Purchase Invoice and left on
        its timeline. A row already in agreement is untouched.
        """
        pinv = create_purchase_invoice(
            bill_no="SYNC-PI-001",
            bill_date="2024-02-01",
            posting_date="2024-02-01",
        )
        gst_is = create_gst_inward_supply(
            bill_no="SYNC-PI-001-A",
            bill_date="2024-02-05",
            return_period_2b="022024",
        )

        matched_pinv = create_purchase_invoice(
            bill_no="SYNC-PI-002",
            bill_date="2024-02-01",
            posting_date="2024-02-01",
        )
        matched_gst_is = create_gst_inward_supply(
            bill_no="SYNC-PI-002",
            bill_date="2024-02-01",
            return_period_2b="022024",
        )

        prt = self.get_reconciliation_tool()
        for purchase, inward_supply in (
            (pinv, gst_is),
            (matched_pinv, matched_gst_is),
        ):
            prt.link_documents(purchase.name, inward_supply.name, "Purchase Invoice")

        result = prt.sync_details(
            [
                {
                    "purchase_invoice_name": pinv.name,
                    "inward_supply_name": gst_is.name,
                    "purchase_doctype": "Purchase Invoice",
                },
                {
                    "purchase_invoice_name": matched_pinv.name,
                    "inward_supply_name": matched_gst_is.name,
                    "purchase_doctype": "Purchase Invoice",
                },
            ],
            fields=["bill_no", "bill_date"],
        )

        self.assertEqual(
            frappe.db.get_value("Purchase Invoice", pinv.name, ["bill_no", "bill_date"], as_dict=True),
            {"bill_no": "SYNC-PI-001-A", "bill_date": getdate("2024-02-05")},
        )

        # db.set_value writes no version, so the comment is what shows on the timeline
        comments = frappe.get_all(
            "Comment",
            filters={
                "reference_doctype": "Purchase Invoice",
                "reference_name": pinv.name,
                "comment_type": "Info",
                "content": ("like", "%Purchase Reconciliation Tool%"),
            },
            pluck="content",
        )
        self.assertEqual(len(comments), 1)
        self.assertIn("SYNC-PI-001-A", comments[0])

        # set_value adds modified / modified_by to the dict it is given, those are not changes
        self.assertNotIn("Last Updated", comments[0])

        # nothing changed on the row already in agreement, so it gets no sync comment
        self.assertFalse(
            frappe.db.exists(
                "Comment",
                {
                    "reference_doctype": "Purchase Invoice",
                    "reference_name": matched_pinv.name,
                    "content": ("like", "%Purchase Reconciliation Tool%"),
                },
            )
        )

        # already in agreement: nothing written, nothing returned
        self.assertEqual(frappe.db.get_value("Purchase Invoice", matched_pinv.name, "bill_no"), "SYNC-PI-002")
        self.assertEqual([row.purchase_invoice_name for row in result], [pinv.name])

    def test_sync_details_for_a_single_field(self):
        """
        The detail view syncs one field at a time, so the other must be left alone.
        """
        pinv = create_purchase_invoice(
            bill_no="SYNC-PI-003",
            bill_date="2024-02-01",
            posting_date="2024-02-01",
        )
        gst_is = create_gst_inward_supply(
            bill_no="SYNC-PI-003-A",
            bill_date="2024-02-07",
            return_period_2b="022024",
        )

        prt = self.get_reconciliation_tool()
        prt.link_documents(pinv.name, gst_is.name, "Purchase Invoice")

        row = {
            "purchase_invoice_name": pinv.name,
            "inward_supply_name": gst_is.name,
            "purchase_doctype": "Purchase Invoice",
        }
        # the dialog sends its checked fields over the wire, so they arrive json encoded
        prt.sync_details(json.dumps([row]), fields=json.dumps(["bill_date"]))

        booked = frappe.db.get_value("Purchase Invoice", pinv.name, ["bill_no", "bill_date"], as_dict=True)
        self.assertEqual(booked.bill_date, getdate("2024-02-07"))
        self.assertEqual(booked.bill_no, "SYNC-PI-003")

        # an unrecognised field must throw an error and not fall back to syncing everything
        with self.assertRaises(frappe.exceptions.ValidationError):
            prt.sync_details([row], fields=["supplier_gstin"])
        self.assertEqual(frappe.db.get_value("Purchase Invoice", pinv.name, "bill_no"), "SYNC-PI-003")

    def test_sync_details_skips_docs_without_differences(self):
        """
        A document syncs only when at least one of the requested fields differs.
        Differences in fields that were not requested don't count.
        """
        # all requested fields already in agreement
        agreed_pinv = create_purchase_invoice(
            bill_no="SYNC-PI-004",
            bill_date="2024-02-01",
            posting_date="2024-02-01",
        )
        agreed_gst_is = create_gst_inward_supply(
            bill_no="SYNC-PI-004",
            bill_date="2024-02-01",
            return_period_2b="022024",
        )

        # bill_no differs, but only bill_date will be requested
        pinv = create_purchase_invoice(
            bill_no="SYNC-PI-005",
            bill_date="2024-02-01",
            posting_date="2024-02-01",
        )
        gst_is = create_gst_inward_supply(
            bill_no="SYNC-PI-005-A",
            bill_date="2024-02-01",
            return_period_2b="022024",
        )

        prt = self.get_reconciliation_tool()
        for purchase, inward_supply in (
            (agreed_pinv, agreed_gst_is),
            (pinv, gst_is),
        ):
            prt.link_documents(purchase.name, inward_supply.name, "Purchase Invoice")

        with self.assertRaises(frappe.exceptions.ValidationError):
            prt.sync_details(
                [
                    {
                        "purchase_invoice_name": agreed_pinv.name,
                        "inward_supply_name": agreed_gst_is.name,
                        "purchase_doctype": "Purchase Invoice",
                    },
                ],
                fields=["bill_no", "bill_date"],
            )

        with self.assertRaises(frappe.exceptions.ValidationError):
            prt.sync_details(
                [
                    {
                        "purchase_invoice_name": pinv.name,
                        "inward_supply_name": gst_is.name,
                        "purchase_doctype": "Purchase Invoice",
                    },
                ],
                fields=["bill_date"],
            )

        # nothing written, nothing logged on either document
        for purchase_name, bill_no in ((agreed_pinv.name, "SYNC-PI-004"), (pinv.name, "SYNC-PI-005")):
            self.assertEqual(
                frappe.db.get_value(
                    "Purchase Invoice", purchase_name, ["bill_no", "bill_date"], as_dict=True
                ),
                {"bill_no": bill_no, "bill_date": getdate("2024-02-01")},
            )
            self.assertFalse(
                frappe.db.exists(
                    "Comment",
                    {
                        "reference_doctype": "Purchase Invoice",
                        "reference_name": purchase_name,
                        "comment_type": "Info",
                        "content": ("like", "%Purchase Reconciliation Tool%"),
                    },
                )
            )

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_sync_details_for_bill_of_entry(self):
        """
        A Bill of Entry carries the bill no / date on its own fields, so the sync must
        write there instead.
        """
        boe = create_boe(bill_no="SYNC-BOE-001")
        gst_is = create_gst_inward_supply(
            bill_no="SYNC-BOE-001-A",
            bill_date="2023-12-15",
            classification="IMPG",
            return_period_2b="122023",
        )

        matched_boe = create_boe(bill_no="SYNC-BOE-002")
        matched_gst_is = create_gst_inward_supply(
            bill_no="SYNC-BOE-002",
            bill_date=matched_boe.bill_of_entry_date,
            classification="IMPG",
            return_period_2b="122023",
        )

        prt = self.get_reconciliation_tool()
        for purchase, inward_supply in (
            (boe, gst_is),
            (matched_boe, matched_gst_is),
        ):
            prt.link_documents(purchase.name, inward_supply.name, "Bill of Entry")

        result = prt.sync_details(
            [
                {
                    "purchase_invoice_name": boe.name,
                    "inward_supply_name": gst_is.name,
                    "purchase_doctype": "Bill of Entry",
                },
                {
                    "purchase_invoice_name": matched_boe.name,
                    "inward_supply_name": matched_gst_is.name,
                    "purchase_doctype": "Bill of Entry",
                },
            ],
            fields=["bill_no", "bill_date"],
        )

        self.assertEqual(
            frappe.db.get_value(
                "Bill of Entry",
                boe.name,
                ["bill_of_entry_no", "bill_of_entry_date"],
                as_dict=True,
            ),
            {"bill_of_entry_no": "SYNC-BOE-001-A", "bill_of_entry_date": getdate("2023-12-15")},
        )

        self.assertTrue(
            frappe.db.exists(
                "Comment",
                {
                    "reference_doctype": "Bill of Entry",
                    "reference_name": boe.name,
                    "comment_type": "Info",
                },
            )
        )

        # already in agreement: nothing written, nothing returned
        self.assertEqual(
            frappe.db.get_value("Bill of Entry", matched_boe.name, "bill_of_entry_no"),
            "SYNC-BOE-002",
        )
        self.assertEqual([row.purchase_invoice_name for row in result], [boe.name])

    def test_sync_details_does_not_blank_booked_values(self):
        """
        The bill no differs but 2A/2B reports no bill date, so only the bill no may be
        written. Whether a document is worth syncing is a per row question, but what to
        write is a per field one.
        """
        prt = self.get_reconciliation_tool()
        pinv, gst_is = self.get_fixture_pair("BILL-23-00040")  # reported bill no BILL-23-00045

        frappe.db.set_value("GST Inward Supply", gst_is, "bill_date", None)
        self.addCleanup(frappe.db.set_value, "GST Inward Supply", gst_is, "bill_date", "2023-12-11")

        prt.sync_details([self.sync_row(pinv, gst_is)], fields=["bill_no", "bill_date"])

        self.assertEqual(
            frappe.db.get_value("Purchase Invoice", pinv, ["bill_no", "bill_date"], as_dict=True),
            {"bill_no": "BILL-23-00045", "bill_date": getdate("2023-12-11")},
        )

    def test_sync_details_uses_the_stored_link_doctype(self):
        """
        purchase_doctype comes off a grid row that may be stale or missing. The stored
        link_doctype is what decides where the values are booked.
        """
        prt = self.get_reconciliation_tool()
        boe, gst_is = self.get_fixture_pair("BILL-23-00011")  # a Bill of Entry pair

        frappe.db.set_value("GST Inward Supply", gst_is, "bill_no", "BILL-23-00011-A")
        self.addCleanup(frappe.db.set_value, "GST Inward Supply", gst_is, "bill_no", "BILL-23-00011")

        row = self.sync_row(boe, gst_is)
        row.pop("purchase_doctype")

        result = prt.sync_details([row], fields=["bill_no"])

        self.assertEqual(frappe.db.get_value("Bill of Entry", boe, "bill_of_entry_no"), "BILL-23-00011-A")
        self.assertEqual([row.purchase_invoice_name for row in result], [boe])

    def get_fixture_pair(self, bill_no):
        """(purchase, inward supply) of a linked pair created from the shared test json"""
        for names, row in self.reconciled_data.items():
            if row.get("bill_no") == bill_no:
                return names

        self.fail(f"No test fixture with bill no {bill_no}")

    def sync_row(self, purchase_name, inward_supply_name):
        """a grid row as the client sends it to sync_details"""
        return {
            "purchase_invoice_name": purchase_name,
            "inward_supply_name": inward_supply_name,
            "purchase_doctype": frappe.db.get_value("GST Inward Supply", inward_supply_name, "link_doctype"),
        }

    def get_reconciliation_tool(self):
        prt = frappe.get_doc("Purchase Reconciliation Tool")
        prt.update(
            {
                "company_gstin": "24AAQCA8719H1ZC",
                "period": "Custom",
                "from_date": "2023-12-01",
                "to_date": "2024-02-29",
                "gst_return": "GSTR 2B",
            }
        )
        # rebuilds ReconciledData for these filters, as the tool does on Generate
        prt.reconcile_and_generate_data()

        return prt

    def test_cdnr_debit_note_matches_regular_purchase_invoice(self):
        """
        A supplier's debit note is booked as a regular purchase invoice (not a
        return), so CDNR must not be limited to purchase returns.
        """
        pinv = create_purchase_invoice(
            bill_no="DN-23-00001",
            bill_date="2023-07-15",
            posting_date="2023-07-15",
        )

        gst_is = create_gst_inward_supply(
            bill_no="DN-23-00001",
            bill_date="2023-07-15",
            classification="CDNR",
            doc_type="Debit Note",
            return_period_2b="072023",
        )

        prt = frappe.get_doc("Purchase Reconciliation Tool")
        prt.update(
            {
                "company_gstin": "24AAQCA8719H1ZC",
                "period": "Custom",
                "from_date": "2023-07-01",
                "to_date": "2023-07-31",
                "gst_return": "GSTR 2B",
            }
        )
        prt.reconcile_and_generate_data()

        self.assertEqual(frappe.db.get_value("GST Inward Supply", gst_is.name, "link_name"), pinv.name)

    def test_purchase_posted_after_period_is_not_matched(self):
        """
        A purchase booked after the period ends must stay out of that period's run.
        It matches once the period covers its posting date.
        """
        # own amounts, so no other invoice can claim these by a residual match
        pinv = create_purchase_invoice(
            bill_no="LATE-ENTRY-001",
            bill_date="2024-01-15",
            posting_date="2024-02-05",
            qty=3,
        )
        gst_is = create_gst_inward_supply(
            bill_no="LATE-ENTRY-001",
            bill_date="2024-01-15",
            return_period_2b="012024",
            items=[{"taxable_value": 3000, "rate": 18, "sgst": 270, "cgst": 270}],
            document_value=3540,
        )

        prt = frappe.get_doc("Purchase Reconciliation Tool")
        prt.update(
            {
                "company_gstin": "24AAQCA8719H1ZC",
                "period": "Custom",
                "from_date": "2024-01-01",
                "to_date": "2024-01-31",
                "gst_return": "GSTR 2B",
            }
        )
        prt.reconcile_and_generate_data()

        self.assertFalse(frappe.db.get_value("GST Inward Supply", gst_is.name, "link_name"))
        self.assertEqual(
            frappe.db.get_value("Purchase Invoice", pinv.name, "reconciliation_status"),
            "Unreconciled",
        )

        # stretch the period past the posting date, now it is in scope
        prt.to_date = "2024-02-29"
        prt.reconcile_and_generate_data()

        self.assertEqual(frappe.db.get_value("GST Inward Supply", gst_is.name, "link_name"), pinv.name)


def create_purchase_invoice(**kwargs):
    args = PURCHASE_INVOICE_DEFAULT_ARGS.copy()
    args.update(kwargs)

    return _create_purchase_invoice(**args).submit()


def create_gst_inward_supply(**kwargs):
    args = INWARD_SUPPLY_DEFAULT_ARGS.copy()
    args.update(kwargs)

    gst_inward_supply = frappe.new_doc("GST Inward Supply")
    gst_inward_supply.update(args)

    for field in ["taxable_value", "igst", "cgst", "sgst", "cess"]:
        gst_inward_supply.set(
            field,
            sum([row.get(field) for row in gst_inward_supply.get("items") if row.get(field)]),
        )

    return gst_inward_supply.insert()


def create_boe(**kwargs):
    kwargs.update(BILL_OF_ENTRY_DEFAULT_ARGS)

    pi = create_purchase_invoice(**kwargs)
    pi.submit()
    boe = make_bill_of_entry(pi.name)
    boe.update(
        {
            "bill_of_entry_no": pi.bill_no,
            "bill_of_entry_date": pi.bill_date,
            "posting_date": pi.posting_date,
        }
    )

    return boe.save(ignore_permissions=True).submit()
