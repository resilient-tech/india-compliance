# Copyright (c) 2022, Resilient Tech and Contributors
# See license.txt

import datetime

import frappe
from frappe.test_runner import make_test_objects
from frappe.tests.utils import FrappeTestCase

from india_compliance.gst_india.doctype.bill_of_entry.bill_of_entry import (
    make_bill_of_entry,
)
from india_compliance.gst_india.utils.tests import (
    create_purchase_invoice as _create_purchase_invoice,
)

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


class TestPurchaseReconciliationTool(FrappeTestCase):
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
                "company": "_Test Indian Registered Company",
                "company_gstin": "All",
                "purchase_from_date": "2023-11-01",
                "purchase_to_date": "2023-12-31",
                "inward_supply_from_date": "2023-11-01",
                "inward_supply_to_date": "2023-12-31",
                "gst_return": "GSTR 2B",
            }
        )

        purchase_reconciliation_tool.save(ignore_permissions=True)
        reconciled_data = purchase_reconciliation_tool.ReconciledData.get()

        for row in reconciled_data:
            for key, value in row.items():
                if isinstance(value, datetime.date):
                    row[key] = str(value)

        for row in reconciled_data:
            self.assertDictEqual(
                row,
                self.reconciled_data.get(
                    (row.purchase_invoice_name, row.inward_supply_name)
                )
                or {},
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

                cls.reconciled_data[(pi.get("name"), gst_is.get("name"))] = (
                    _reconciled_data
                )

        frappe.db.set_single_value("GST Settings", "enable_overseas_transactions", 0)


def create_purchase_invoice(**kwargs):
    args = PURCHASE_INVOICE_DEFAULT_ARGS.copy()
    args.update(kwargs)

    return _create_purchase_invoice(**args).submit()


def create_gst_inward_supply(**kwargs):
    args = INWARD_SUPPLY_DEFAULT_ARGS.copy()
    args.update(kwargs)

    gst_inward_supply = frappe.new_doc("GST Inward Supply")

    gst_inward_supply.update(args)

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
