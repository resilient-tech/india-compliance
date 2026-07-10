# Copyright (c) 2022, Resilient Tech and Contributors
# See license.txt

import datetime

import frappe
from frappe.tests import IntegrationTestCase
from frappe.tests.utils import make_test_objects

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
                "purchase_period": "Custom",
                "purchase_from_date": "2023-11-01",
                "purchase_to_date": "2023-12-31",
                "inward_supply_period": "Custom",
                "inward_supply_from_date": "2023-11-01",
                "inward_supply_to_date": "2023-12-31",
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
                "purchase_period": "Custom",
                "purchase_from_date": "2023-09-01",
                "purchase_to_date": "2023-09-30",
                "inward_supply_period": "Custom",
                "inward_supply_from_date": "2023-09-01",
                "inward_supply_to_date": "2024-01-31",
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
                "purchase_period": "Custom",
                "purchase_from_date": "2023-10-01",
                "purchase_to_date": "2023-10-31",
                "inward_supply_period": "Custom",
                "inward_supply_from_date": "2023-10-01",
                "inward_supply_to_date": "2023-10-31",
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
                "purchase_period": "Custom",
                "purchase_from_date": "2024-01-01",
                "purchase_to_date": "2024-01-31",
                "inward_supply_period": "Custom",
                "inward_supply_from_date": "2023-10-01",
                "inward_supply_to_date": "2024-01-31",
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
                "purchase_period": "Custom",
                "purchase_from_date": "2023-10-01",
                "purchase_to_date": "2023-10-31",
                "inward_supply_period": "Custom",
                "inward_supply_from_date": "2023-10-01",
                "inward_supply_to_date": "2023-10-31",
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
                "purchase_period": "Custom",
                "purchase_from_date": "2023-08-01",
                "purchase_to_date": "2023-08-31",
                "inward_supply_period": "Custom",
                "inward_supply_from_date": "2023-08-01",
                "inward_supply_to_date": "2023-09-30",
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
                "purchase_period": "Custom",
                "purchase_from_date": "2024-01-01",
                "purchase_to_date": "2024-01-31",
                "inward_supply_period": "Custom",
                "inward_supply_from_date": "2024-01-01",
                "inward_supply_to_date": "2024-01-31",
                "gst_return": "GSTR 2B",
            }
        )
        prt.reconcile_and_generate_data()

        result = prt.get_invoice_details(
            purchase_name=pinv.name,
            inward_supply_name=None,
        )

        self.assertEqual(result.purchase_invoice_name, pinv.name)
        self.assertEqual(result.match_status, "Missing in 2A/2B")
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
                "purchase_period": "Custom",
                "purchase_from_date": "2024-01-01",
                "purchase_to_date": "2024-01-31",
                "inward_supply_period": "Custom",
                "inward_supply_from_date": "2024-01-01",
                "inward_supply_to_date": "2024-01-31",
                "gst_return": "GSTR 2B",
            }
        )
        prt.reconcile_and_generate_data()

        result = prt.get_invoice_details(
            purchase_name=None,
            inward_supply_name=gst_is.name,
        )

        self.assertEqual(result.inward_supply_name, gst_is.name)
        self.assertEqual(result.match_status, "Missing in PI")
        self.assertIsNone(result.purchase_invoice_name)

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
                "purchase_period": "Custom",
                "purchase_from_date": "2024-01-01",
                "purchase_to_date": "2024-01-31",
                "inward_supply_period": "Custom",
                "inward_supply_from_date": "2024-01-01",
                "inward_supply_to_date": "2024-01-31",
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
                "purchase_period": "Custom",
                "purchase_from_date": "2024-01-01",
                "purchase_to_date": "2024-01-31",
                "inward_supply_period": "Custom",
                "inward_supply_from_date": "2024-01-01",
                "inward_supply_to_date": "2024-01-31",
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
                "purchase_period": "Custom",
                "purchase_from_date": "2024-01-01",
                "purchase_to_date": "2024-01-31",
                "inward_supply_period": "Custom",
                "inward_supply_from_date": "2024-01-01",
                "inward_supply_to_date": "2024-01-31",
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
