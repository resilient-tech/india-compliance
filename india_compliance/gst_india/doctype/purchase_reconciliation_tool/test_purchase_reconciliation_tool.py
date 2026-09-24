# Copyright (c) 2022, Resilient Tech and Contributors
# See license.txt

import datetime
import json

import frappe
from frappe.tests import IntegrationTestCase, change_settings
from frappe.tests.utils import make_test_objects
from frappe.utils import formatdate, getdate

from india_compliance.gst_india.doctype.bill_of_entry.bill_of_entry import (
    make_bill_of_entry,
)
from india_compliance.gst_india.doctype.purchase_reconciliation_tool.purchase_reconciliation_tool import (
    BuildExcel,
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

        matched = 0

        for row in reconciled_data:
            expected = self.reconciled_data.get((row.purchase_invoice_name, row.inward_supply_name))
            if not expected:
                continue

            self.assertDictEqual(row, expected)
            matched += 1

        self.assertEqual(matched, len(self.reconciled_data))

        matched_row = next(
            row for row in reconciled_data if row.purchase_invoice_name and row.inward_supply_name
        )
        details = purchase_reconciliation_tool.get_invoice_details(
            matched_row.purchase_invoice_name, matched_row.inward_supply_name
        )

        self.assertEqual(details._inward_supply.return_period_2b, "122023")
        self.assertEqual(details._purchase_invoice.itc_claim_period, "122023")

        exported_fields = [
            column["fieldname"] for column in BuildExcel(purchase_reconciliation_tool, {}).invoice_header
        ]

        self.assertIn("return_period_2b", exported_fields)
        self.assertIn("itc_claim_period", exported_fields)

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

    def test_copy_details_for_purchase_invoice(self):
        prt = self.get_reconciliation_tool()
        pinv, gst_is = self.get_fixture_pair("BILL-2324-50")
        matched_pinv, matched_gst_is = self.get_fixture_pair("BILL-23-00001")
        self.addCleanup(
            frappe.db.set_value,
            "Purchase Invoice",
            pinv,
            {"bill_no": "BILL-2324-50", "bill_date": "2023-12-11"},
        )

        result = prt.copy_details(
            [
                self.format_data_for_copy(pinv, gst_is),
                self.format_data_for_copy(matched_pinv, matched_gst_is),
            ],
            fields=["bill_no", "bill_date"],
        )
        self.assertEqual(
            frappe.db.get_value("Purchase Invoice", pinv, ["bill_no", "bill_date"], as_dict=True),
            {"bill_no": "BILL-23-24-50", "bill_date": getdate("2023-12-18")},
        )
        self.assertEqual(
            get_copy_version("Purchase Invoice", pinv),
            {"bill_no": "BILL-23-24-50", "bill_date": formatdate("2023-12-18")},
        )
        self.assertIsNone(get_copy_version("Purchase Invoice", matched_pinv))
        self.assertEqual(frappe.db.get_value("Purchase Invoice", matched_pinv, "bill_no"), "BILL-23-00001")
        self.assertEqual([row.purchase_invoice_name for row in result], [pinv])

    def test_copy_details_for_a_single_field(self):
        prt = self.get_reconciliation_tool()
        pinv, gst_is = self.get_fixture_pair("BILL-2324-50")
        self.addCleanup(frappe.db.set_value, "Purchase Invoice", pinv, "bill_date", "2023-12-11")

        row = self.format_data_for_copy(pinv, gst_is)
        prt.copy_details(json.dumps([row]), fields=json.dumps(["bill_date"]))

        self.assertEqual(
            frappe.db.get_value("Purchase Invoice", pinv, ["bill_no", "bill_date"], as_dict=True),
            {"bill_no": "BILL-2324-50", "bill_date": getdate("2023-12-18")},
        )
        with self.assertRaises(frappe.ValidationError):
            prt.copy_details([row], fields=["supplier_gstin"])
        self.assertEqual(frappe.db.get_value("Purchase Invoice", pinv, "bill_no"), "BILL-2324-50")

    def test_copy_details_for_bill_of_entry(self):
        prt = self.get_reconciliation_tool()
        boe, gst_is = self.get_fixture_pair("BILL-23-00012")
        matched_boe, matched_gst_is = self.get_fixture_pair("BILL-23-00011")
        self.addCleanup(
            frappe.db.set_value,
            "Bill of Entry",
            boe,
            {"bill_of_entry_no": "BILL-23-00012", "bill_of_entry_date": "2023-12-11"},
        )

        result = prt.copy_details(
            [self.format_data_for_copy(boe, gst_is), self.format_data_for_copy(matched_boe, matched_gst_is)],
            fields=["bill_no", "bill_date"],
        )

        self.assertEqual(
            frappe.db.get_value(
                "Bill of Entry",
                boe,
                ["bill_of_entry_no", "bill_of_entry_date"],
                as_dict=True,
            ),
            {"bill_of_entry_no": "BILL-23-00012-A", "bill_of_entry_date": getdate("2023-12-15")},
        )

        self.assertEqual(
            get_copy_version("Bill of Entry", boe),
            {"bill_of_entry_no": "BILL-23-00012-A", "bill_of_entry_date": formatdate("2023-12-15")},
        )
        self.assertEqual(
            frappe.db.get_value("Bill of Entry", matched_boe, "bill_of_entry_no"), "BILL-23-00011"
        )
        self.assertIsNone(get_copy_version("Bill of Entry", matched_boe))
        self.assertEqual([row.purchase_invoice_name for row in result], [boe])

    def test_copy_details_bulk(self):
        prt = self.get_reconciliation_tool()
        pinv, pinv_gst_is = self.get_fixture_pair("BILL-2324-50")
        boe, boe_gst_is = self.get_fixture_pair("BILL-23-00012")
        blocked_pinv, blocked_gst_is = self.get_fixture_pair("BILL-23-00040")
        frappe.db.set_value("GST Inward Supply", blocked_gst_is, "bill_no", "BILL-23-00001")
        self.addCleanup(frappe.db.set_value, "GST Inward Supply", blocked_gst_is, "bill_no", "BILL-23-00045")
        self.addCleanup(
            frappe.db.set_value,
            "Purchase Invoice",
            pinv,
            {"bill_no": "BILL-2324-50", "bill_date": "2023-12-11"},
        )
        self.addCleanup(
            frappe.db.set_value,
            "Bill of Entry",
            boe,
            {"bill_of_entry_no": "BILL-23-00012", "bill_of_entry_date": "2023-12-11"},
        )

        with change_settings("Accounts Settings", {"check_supplier_invoice_uniqueness": 1}):
            result = prt.copy_details(
                [
                    self.format_data_for_copy(blocked_pinv, blocked_gst_is),
                    self.format_data_for_copy(pinv, pinv_gst_is),
                    self.format_data_for_copy(boe, boe_gst_is),
                ],
                fields=["bill_no", "bill_date"],
            )

        self.assertEqual(
            frappe.db.get_value("Purchase Invoice", pinv, ["bill_no", "bill_date"], as_dict=True),
            {"bill_no": "BILL-23-24-50", "bill_date": getdate("2023-12-18")},
        )
        self.assertEqual(
            get_copy_version("Purchase Invoice", pinv),
            {"bill_no": "BILL-23-24-50", "bill_date": formatdate("2023-12-18")},
        )

        self.assertEqual(
            frappe.db.get_value(
                "Bill of Entry",
                boe,
                ["bill_of_entry_no", "bill_of_entry_date"],
                as_dict=True,
            ),
            {"bill_of_entry_no": "BILL-23-00012-A", "bill_of_entry_date": getdate("2023-12-15")},
        )
        self.assertEqual(
            get_copy_version("Bill of Entry", boe),
            {"bill_of_entry_no": "BILL-23-00012-A", "bill_of_entry_date": formatdate("2023-12-15")},
        )
        self.assertEqual(frappe.db.get_value("Purchase Invoice", blocked_pinv, "bill_no"), "BILL-23-00040")
        messages = frappe.as_json(frappe.get_message_log())
        self.assertIn(blocked_pinv, messages)
        self.assertIn("Supplier Invoice No exists in Purchase Invoice", messages)

        self.assertEqual({row.purchase_invoice_name for row in result}, {pinv, boe})

    def test_copy_details_uses_the_stored_link_doctype(self):
        """
        The grid row carries a purchase_doctype, but the server never reads it. The
        link_doctype stored on the GST Inward Supply decides whether the values land on
        a Purchase Invoice or a Bill of Entry, so a missing or stale value on the row
        cannot misroute the write.
        """
        prt = self.get_reconciliation_tool()
        boe, gst_is = self.get_fixture_pair("BILL-23-00011")

        frappe.db.set_value("GST Inward Supply", gst_is, "bill_no", "BILL-23-00011-A")
        self.addCleanup(frappe.db.set_value, "GST Inward Supply", gst_is, "bill_no", "BILL-23-00011")
        self.addCleanup(frappe.db.set_value, "Bill of Entry", boe, "bill_of_entry_no", "BILL-23-00011")

        row = self.format_data_for_copy(boe, gst_is)
        row.pop("purchase_doctype")

        result = prt.copy_details([row], fields=["bill_no"])

        self.assertEqual(frappe.db.get_value("Bill of Entry", boe, "bill_of_entry_no"), "BILL-23-00011-A")
        self.assertEqual([row.purchase_invoice_name for row in result], [boe])

    def test_copy_details_permission_checks(self):
        """
        Two gates, both checked before anything is written.

        Company: a user restricted to another company cannot copy onto a purchase
        booked elsewhere, and can once that company is permitted.

        Field: bill_no on Purchase Invoice sits at permlevel 1, so a user without
        Accounts Manager cannot write it. One such row blocks the whole batch, so the
        Bill of Entry row the user could write stays untouched too.
        """
        prt = self.get_reconciliation_tool()
        boe, boe_gst_is = self.get_fixture_pair("BILL-23-00011")
        pinv, pinv_gst_is = self.get_fixture_pair("BILL-23-00040")

        frappe.db.set_value("GST Inward Supply", boe_gst_is, "bill_no", "BILL-23-00011-A")
        self.addCleanup(frappe.db.set_value, "GST Inward Supply", boe_gst_is, "bill_no", "BILL-23-00011")
        self.addCleanup(frappe.db.set_value, "Bill of Entry", boe, "bill_of_entry_no", "BILL-23-00011")
        self.addCleanup(frappe.db.set_value, "Purchase Invoice", pinv, "bill_no", "BILL-23-00040")

        test_user = frappe.get_doc("User", "test@example.com")
        test_user.add_roles("Accounts User")
        self.addCleanup(test_user.remove_roles, "Accounts User")
        self.addCleanup(frappe.clear_cache, user=test_user.name)
        frappe.clear_cache(user=test_user.name)

        rows = [self.format_data_for_copy(pinv, pinv_gst_is)]
        user_permission = frappe.get_doc(
            {
                "doctype": "User Permission",
                "user": test_user.name,
                "allow": "Company",
                "for_value": "_Test Indian Unregistered Company",
            }
        ).insert(ignore_permissions=True)
        frappe.clear_cache(user=test_user.name)

        with self.set_user(test_user.name):
            self.assertRaises(frappe.PermissionError, prt.copy_details, rows, ["bill_no"])

        self.assertEqual(frappe.db.get_value("Purchase Invoice", pinv, "bill_no"), "BILL-23-00040")
        user_permission.db_set("for_value", "_Test Indian Registered Company")
        frappe.clear_cache(user=test_user.name)

        with self.set_user(test_user.name):
            prt.copy_details(rows, ["bill_no"])

        self.assertEqual(frappe.db.get_value("Purchase Invoice", pinv, "bill_no"), "BILL-23-00045")
        self.assertEqual(get_copy_version("Purchase Invoice", pinv), {"bill_no": "BILL-23-00045"})

        user_permission.delete(ignore_permissions=True)
        frappe.db.set_value("Purchase Invoice", pinv, "bill_no", "BILL-23-00040")
        test_user.remove_roles("Accounts Manager")
        self.addCleanup(test_user.add_roles, "Accounts Manager")
        frappe.clear_cache(user=test_user.name)
        frappe.make_property_setter(
            {
                "doctype": "Purchase Invoice",
                "fieldname": "bill_no",
                "property": "permlevel",
                "value": 1,
                "property_type": "Int",
            },
            validate_fields_for_doctype=False,
        )
        self.addCleanup(frappe.clear_cache, doctype="Purchase Invoice")
        self.addCleanup(frappe.db.delete, "Property Setter", {"doc_type": "Purchase Invoice"})
        frappe.clear_cache(doctype="Purchase Invoice")

        rows = [self.format_data_for_copy(boe, boe_gst_is), self.format_data_for_copy(pinv, pinv_gst_is)]

        with self.set_user(test_user.name):
            self.assertRaises(frappe.PermissionError, prt.copy_details, rows, ["bill_no"])
        self.assertEqual(frappe.db.get_value("Bill of Entry", boe, "bill_of_entry_no"), "BILL-23-00011")
        self.assertEqual(frappe.db.get_value("Purchase Invoice", pinv, "bill_no"), "BILL-23-00040")
        self.assertIsNone(get_copy_version("Bill of Entry", boe))

    def get_fixture_pair(self, bill_no):
        for names, row in self.reconciled_data.items():
            if row.get("bill_no") == bill_no:
                return names

        self.fail(f"No test fixture with bill no {bill_no}")

    def format_data_for_copy(self, purchase_name, inward_supply_name):
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

        # a debit note adds to the ITC, so it stays positive on both sides
        detail = prt.get_invoice_details(pinv.name, gst_is.name)
        self.assertEqual(detail._purchase_invoice.taxable_value, 10000)
        self.assertEqual(detail._inward_supply.taxable_value, 10000)

    def test_cdnr_credit_note_is_signed_on_both_sides(self):
        """
        A supplier's credit note reduces the ITC. It is booked as a return invoice,
        so both sides must report it negative and difference out to zero.
        """
        pinv = create_purchase_invoice(
            bill_no="CN-23-00001",
            bill_date="2023-09-15",
            posting_date="2023-09-15",
            is_return=1,
            qty=-5,
        )

        gst_is = create_gst_inward_supply(
            bill_no="CN-23-00001",
            bill_date="2023-09-15",
            classification="CDNR",
            doc_type="Credit Note",
            return_period_2b="092023",
            # 2A/2B reports note values as positive
            items=[{"taxable_value": 5000, "rate": 18, "sgst": 450, "cgst": 450}],
            document_value=5900,
        )

        prt = frappe.get_doc("Purchase Reconciliation Tool")
        prt.update(
            {
                "company_gstin": "24AAQCA8719H1ZC",
                "period": "Custom",
                "from_date": "2023-09-01",
                "to_date": "2023-09-30",
                "gst_return": "GSTR 2B",
            }
        )
        rows = [row for row in prt.reconcile_and_generate_data() if row.purchase_invoice_name == pinv.name]

        self.assertEqual(frappe.db.get_value("GST Inward Supply", gst_is.name, "link_name"), pinv.name)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].classification, "CDNR")
        self.assertEqual(rows[0].taxable_value_difference, 0)
        self.assertEqual(rows[0].tax_difference, 0)

        detail = prt.get_invoice_details(pinv.name, gst_is.name)
        purchase, inward_supply = detail._purchase_invoice, detail._inward_supply

        self.assertEqual(purchase.taxable_value, -5000)
        self.assertEqual(purchase.cgst, -450)
        self.assertEqual(purchase.sgst, -450)

        self.assertEqual(inward_supply.taxable_value, -5000)
        self.assertEqual(inward_supply.cgst, -450)
        self.assertEqual(inward_supply.sgst, -450)

    def test_credit_note_nets_off_the_invoice_in_books(self):
        """
        An invoice and its credit note, neither reported in 2A/2B, must net to the
        amount actually claimable rather than adding up to the gross.
        """
        dates = {"bill_date": "2023-10-15", "posting_date": "2023-10-15"}

        # own amounts, so no other invoice can claim these by a residual match
        invoice = create_purchase_invoice(bill_no="NET-23-00001", qty=7, rate=1100, **dates)
        credit_note = create_purchase_invoice(bill_no="NET-23-00002", is_return=1, qty=-2, rate=1100, **dates)

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
        rows = {
            row.purchase_invoice_name: row
            for row in prt.reconcile_and_generate_data()
            if row.purchase_invoice_name in (invoice.name, credit_note.name)
        }

        self.assertEqual(len(rows), 2)
        for row in rows.values():
            self.assertEqual(row.match_status, "Only in Books")

        # nothing in 2A/2B, so each difference is the negated book value
        self.assertEqual(rows[invoice.name].taxable_value_difference, -7700)
        self.assertEqual(rows[credit_note.name].taxable_value_difference, 2200)

        # what the summary rolls up: the net claimable, not the gross of both documents
        self.assertEqual(sum(row.taxable_value_difference for row in rows.values()), -5500)
        self.assertEqual(sum(row.tax_difference for row in rows.values()), -990)

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


def get_copy_version(doctype, name, tool="Purchase Reconciliation Tool"):
    version = frappe.db.get_value(
        "Version", {"ref_doctype": doctype, "docname": name}, "data", order_by="creation desc"
    )
    data = json.loads(version or "{}")
    if (data.get("updater_reference") or {}).get("doctype") != tool:
        return None

    return {row[0]: row[2] for row in data["changed"]}


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
