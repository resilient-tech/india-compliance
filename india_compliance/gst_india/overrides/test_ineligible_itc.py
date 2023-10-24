import json
from contextlib import contextmanager

import frappe
from frappe.tests.utils import FrappeTestCase, change_settings
from frappe.utils import today
from erpnext.controllers.sales_and_purchase_return import make_return_doc
from erpnext.stock.doctype.purchase_receipt.purchase_receipt import (
    make_purchase_invoice,
)

from india_compliance.gst_india.doctype.bill_of_entry.bill_of_entry import (
    make_bill_of_entry,
    make_landed_cost_voucher,
)
from india_compliance.gst_india.utils.tests import create_transaction

SAMPLE_ITEM_LIST = [
    {"item_code": "Test Stock Item", "qty": 5, "rate": 20},
    {"item_code": "Test Ineligible Stock Item", "qty": 3, "rate": 19},
    {
        "item_code": "Test Fixed Asset",
        "qty": 1,
        "rate": 1000,
        "asset_location": "Test Location",
    },
    {
        "item_code": "Test Ineligible Fixed Asset",
        "qty": 1,
        "rate": 999,
        "asset_location": "Test Location",
    },
    {"item_code": "Test Service Item", "qty": 3, "rate": 500},
    {"item_code": "Test Ineligible Service Item", "qty": 2, "rate": 499},
]
# Item Total
# 20 * 5 + 19 * 3 + 1000 * 1 + 999 * 1 + 500 * 3 + 499 * 2 + 100 * 1 (Default) = 4754

# Tax Total
# 4754 * 18% = 855.72 or CGST + SGST = 427.86 + 427.86 = 855.72

# Ineligible Stock Item = 19 * 3 * 18% = 10.26 or CGST + SGST = 5.13 + 5.13 = 10.26
# Ineligible Fixed Asset = 999 * 1 * 18% = 179.82 or CGST + SGST = 89.91 + 89.91 = 179.82
# Ineligible Service Item = 499 * 2 * 18% = 179.64 or CGST + SGST = 89.82 + 89.82 = 179.64


@contextmanager
def toggle_perpetual_inventory():
    frappe.db.set_value(
        "Company",
        "_Test Indian Registered Company",
        "enable_perpetual_inventory",
        0,
    )

    if hasattr(frappe.local, "enable_perpetual_inventory"):
        del frappe.local.enable_perpetual_inventory

    try:
        yield

    finally:
        frappe.db.set_value(
            "Company",
            "_Test Indian Registered Company",
            "enable_perpetual_inventory",
            1,
        )

        if hasattr(frappe.local, "enable_perpetual_inventory"):
            del frappe.local.enable_perpetual_inventory


@contextmanager
def toggle_provisional_accounting():
    # Enable Provisional Expense
    frappe.db.set_value(
        "Company",
        "_Test Indian Registered Company",
        {
            "enable_provisional_accounting_for_non_stock_items": 1,
            "default_provisional_account": "Unsecured Loans - _TIRC",
        },
    )

    try:
        yield

    finally:
        frappe.db.set_value(
            "Company",
            "_Test Indian Registered Company",
            {
                "enable_provisional_accounting_for_non_stock_items": 0,
                "default_provisional_account": None,
            },
        )


class TestIneligibleITC(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_test_items()

    def test_purchase_invoice_with_update_stock(self):
        transaction_details = {
            "doctype": "Purchase Invoice",
            "bill_no": "BILL-01",
            "update_stock": 1,
            "items": SAMPLE_ITEM_LIST,
            "is_in_state": 1,
        }

        doc = create_transaction(**transaction_details)

        self.assertEqual(doc.ineligibility_reason, "Ineligible As Per Section 17(5)")

        self.assertGLEntry(
            doc.name,
            [
                {"account": "Round Off - _TIRC", "debit": 0.28, "credit": 0.0},
                {
                    "account": "GST Expense - _TIRC",
                    "debit": 369.72,
                    "credit": 369.72,
                },  # 179.64 + 179.82 + 10.26
                {
                    "account": "Input Tax SGST - _TIRC",
                    "debit": 427.86,
                    "credit": 184.86,  # 369.72 / 2
                },
                {
                    "account": "Input Tax CGST - _TIRC",
                    "debit": 427.86,
                    "credit": 184.86,
                },
                {
                    "account": "Administrative Expenses - _TIRC",
                    "debit": 2677.64,  # 500 * 3 + 499 * 2 + 179.64
                    "credit": 0.0,
                },
                {
                    "account": "CWIP Account - _TIRC",
                    "debit": 2178.82,
                    "credit": 0.0,
                },  # 1000 + 999 + 179.82
                {
                    "account": "Stock In Hand - _TIRC",
                    "debit": 267.26,
                    "credit": 0.0,
                },  # 20 * 5 + 19 * 3 + 100 * 1 + 10.26
                {"account": "Creditors - _TIRC", "debit": 0.0, "credit": 5610.0},
            ],
        )

        self.assertStockValues(
            doc.name, {"Test Stock Item": 20, "Test Ineligible Stock Item": 22.42}
        )
        self.assertAssetValues(
            "Purchase Invoice",
            doc.name,
            {"Test Fixed Asset": 1000, "Test Ineligible Fixed Asset": 1178.82},
        )  # 999 + 179.82

    def test_purchase_invoice_with_ineligible_pos(self):
        transaction_details = {
            "doctype": "Purchase Invoice",
            "bill_no": "BILL-02",
            "update_stock": 1,
            "items": SAMPLE_ITEM_LIST,
            "place_of_supply": "27-Maharashtra",
            "is_out_state": 1,
        }

        doc = create_transaction(**transaction_details)

        self.assertEqual(doc.ineligibility_reason, "ITC restricted due to PoS rules")

        self.assertGLEntry(
            doc.name,
            [
                {"account": "Round Off - _TIRC", "debit": 0.28, "credit": 0.0},
                {
                    "account": "GST Expense - _TIRC",
                    "debit": 855.72,
                    "credit": 855.72,
                },  # full taxes reversed
                {
                    "account": "Input Tax IGST - _TIRC",
                    "debit": 855.72,
                    "credit": 855.72,
                },
                {
                    "account": "Administrative Expenses - _TIRC",
                    "debit": 2947.64,
                    "credit": 0.0,
                },
                {
                    "account": "CWIP Account - _TIRC",
                    "debit": 2358.82,
                    "credit": 0.0,
                },
                {
                    "account": "Stock In Hand - _TIRC",
                    "debit": 303.26,
                    "credit": 0.0,
                },
                {"account": "Creditors - _TIRC", "debit": 0.0, "credit": 5610.0},
            ],
        )

        self.assertStockValues(
            doc.name, {"Test Stock Item": 23.6, "Test Ineligible Stock Item": 22.42}
        )
        self.assertAssetValues(
            "Purchase Invoice",
            doc.name,
            {"Test Fixed Asset": 1180, "Test Ineligible Fixed Asset": 1178.82},
        )

    def test_purchase_receipt_and_then_purchase_invoice(self):
        transaction_details = {
            "doctype": "Purchase Receipt",
            "items": SAMPLE_ITEM_LIST,
            "is_in_state": 1,
        }

        doc = create_transaction(**transaction_details)

        self.assertGLEntry(
            doc.name,
            [
                {
                    "account": "GST Expense - _TIRC",
                    "debit": 0.0,
                    "credit": 190.08,
                },  # 10.26 + 179.82
                {
                    "account": "Asset Received But Not Billed - _TIRC",
                    "debit": 0.0,
                    "credit": 1999.0,
                },
                {
                    "account": "CWIP Account - _TIRC",
                    "debit": 2178.82,  # 1999 + 179.82
                    "credit": 0.0,
                },
                {
                    "account": "Stock Received But Not Billed - _TIRC",
                    "debit": 0.0,
                    "credit": 257.0,
                },
                {
                    "account": "Stock In Hand - _TIRC",
                    "debit": 267.26,  # 257 + 10.26
                    "credit": 0.0,
                },
            ],
        )

        self.assertStockValues(
            doc.name, {"Test Stock Item": 20, "Test Ineligible Stock Item": 22.42}
        )
        self.assertAssetValues(
            "Purchase Receipt",
            doc.name,
            {"Test Fixed Asset": 1000, "Test Ineligible Fixed Asset": 1178.82},
        )

        # Create Purchase Invoice
        doc = make_purchase_invoice(doc.name)
        doc.bill_no = "BILL-03"
        doc.submit()

        self.assertEqual(doc.ineligibility_reason, "Ineligible As Per Section 17(5)")

        self.assertGLEntry(
            doc.name,
            [
                {"account": "Round Off - _TIRC", "debit": 0.28, "credit": 0.0},
                {
                    "account": "GST Expense - _TIRC",
                    "debit": 369.72,  # 179.82 + 179.64 + 10.26
                    "credit": 179.64,  # Only Expense
                },
                {
                    "account": "Input Tax SGST - _TIRC",
                    "debit": 427.86,
                    "credit": 184.86,
                },
                {
                    "account": "Input Tax CGST - _TIRC",
                    "debit": 427.86,
                    "credit": 184.86,  # 369.72 / 2
                },
                {
                    "account": "Asset Received But Not Billed - _TIRC",
                    "debit": 1999.0,
                    "credit": 0.0,
                },
                {
                    "account": "Administrative Expenses - _TIRC",
                    "debit": 2677.64,  # 1500 + 998 + 179.64
                    "credit": 0.0,
                },
                {
                    "account": "Stock Received But Not Billed - _TIRC",
                    "debit": 257.0,
                    "credit": 0.0,
                },
                {"account": "Creditors - _TIRC", "debit": 0.0, "credit": 5610.0},
            ],
        )

    def test_purchase_receipt_and_then_purchase_invoice_for_ineligible_pos(self):
        transaction_details = {
            "doctype": "Purchase Receipt",
            "items": SAMPLE_ITEM_LIST,
            "place_of_supply": "27-Maharashtra",
            "is_out_state": 1,
        }

        doc = create_transaction(**transaction_details)

        self.assertGLEntry(
            doc.name,
            [
                {
                    "account": "GST Expense - _TIRC",
                    "debit": 0.0,
                    "credit": 406.08,
                },  # 855.72 - 449.64 (reversal on expense)
                {
                    "account": "Asset Received But Not Billed - _TIRC",
                    "debit": 0.0,
                    "credit": 1999.0,
                },
                {
                    "account": "CWIP Account - _TIRC",
                    "debit": 2358.82,
                    "credit": 0.0,
                },
                {
                    "account": "Stock Received But Not Billed - _TIRC",
                    "debit": 0.0,
                    "credit": 257.0,
                },
                {
                    "account": "Stock In Hand - _TIRC",
                    "debit": 303.26,
                    "credit": 0.0,
                },
            ],
        )

        self.assertStockValues(
            doc.name,
            {
                "Test Stock Item": 23.6,
                "Test Ineligible Stock Item": 22.42,
            },
        )
        self.assertAssetValues(
            "Purchase Receipt",
            doc.name,
            {"Test Fixed Asset": 1180, "Test Ineligible Fixed Asset": 1178.82},
        )

        # Create Purchase Invoice
        doc = make_purchase_invoice(doc.name)
        doc.bill_no = "BILL-04"
        doc.submit()

        self.assertEqual(doc.ineligibility_reason, "ITC restricted due to PoS rules")

        self.assertGLEntry(
            doc.name,
            [
                {"account": "Round Off - _TIRC", "debit": 0.28, "credit": 0.0},
                {
                    "account": "GST Expense - _TIRC",
                    "debit": 855.72,
                    "credit": 449.64,  # expense reversal
                },
                {
                    "account": "Input Tax IGST - _TIRC",
                    "debit": 855.72,
                    "credit": 855.72,
                },
                {
                    "account": "Asset Received But Not Billed - _TIRC",
                    "debit": 1999.0,
                    "credit": 0.0,
                },
                {
                    "account": "Administrative Expenses - _TIRC",
                    "debit": 2947.64,
                    "credit": 0.0,
                },
                {
                    "account": "Stock Received But Not Billed - _TIRC",
                    "debit": 257.0,
                    "credit": 0.0,
                },
                {"account": "Creditors - _TIRC", "debit": 0.0, "credit": 5610.0},
            ],
        )

    def test_purchase_returns_with_update_stock(self):
        transaction_details = {
            "doctype": "Purchase Invoice",
            "bill_no": "BILL-05",
            "update_stock": 1,
            "items": SAMPLE_ITEM_LIST,
            "is_in_state": 1,
        }

        doc = create_transaction(**transaction_details)
        doc = make_return_doc("Purchase Invoice", doc.name)
        doc.submit()

        self.assertGLEntry(
            doc.name,
            [
                {"account": "Round Off - _TIRC", "debit": 0.0, "credit": 0.28},
                {
                    "account": "GST Expense - _TIRC",
                    "debit": 369.72,
                    "credit": 369.72,
                },
                {
                    "account": "Input Tax SGST - _TIRC",
                    "debit": 0.0,
                    "credit": 243.0,
                },
                {
                    "account": "Input Tax CGST - _TIRC",
                    "debit": 0.0,
                    "credit": 243.0,
                },
                {
                    "account": "CWIP Account - _TIRC",
                    "debit": 0.0,
                    "credit": 2178.82,
                },
                {
                    "account": "Administrative Expenses - _TIRC",
                    "debit": 0.0,
                    "credit": 2677.64,
                },
                {
                    "account": "Stock In Hand - _TIRC",
                    "debit": 0.0,
                    "credit": 267.26,
                },
                {"account": "Creditors - _TIRC", "debit": 5610.0, "credit": 0.0},
            ],
        )

    @toggle_perpetual_inventory()
    def test_purchase_receipt_and_then_purchase_invoice_for_non_perpetual_stock(self):
        transaction_details = {
            "doctype": "Purchase Receipt",
            "items": SAMPLE_ITEM_LIST,
            "is_in_state": 1,
        }

        doc = create_transaction(**transaction_details)
        self.assertGLEntry(
            doc.name,
            [
                {
                    "account": "GST Expense - _TIRC",
                    "debit": 0.0,
                    "credit": 179.82,
                },  # only asset
                {
                    "account": "Asset Received But Not Billed - _TIRC",
                    "debit": 0.0,
                    "credit": 1999.0,
                },
                {
                    "account": "CWIP Account - _TIRC",
                    "debit": 2178.82,
                    "credit": 0.0,
                },
            ],
        )

        self.assertAssetValues(
            doc.doctype,
            doc.name,
            {"Test Fixed Asset": 1000, "Test Ineligible Fixed Asset": 1178.82},
        )

        # Create Purchase Invoice
        doc = make_purchase_invoice(doc.name)
        doc.bill_no = "BILL-06"
        doc.submit()

        self.assertEqual(doc.ineligibility_reason, "Ineligible As Per Section 17(5)")

        self.assertGLEntry(
            doc.name,
            [
                {"account": "Round Off - _TIRC", "debit": 0.28, "credit": 0.0},
                {
                    "account": "GST Expense - _TIRC",
                    "debit": 369.72,
                    "credit": 189.9,
                },
                {
                    "account": "Input Tax SGST - _TIRC",
                    "debit": 427.86,
                    "credit": 184.86,
                },
                {
                    "account": "Input Tax CGST - _TIRC",
                    "debit": 427.86,
                    "credit": 184.86,
                },
                {
                    "account": "Asset Received But Not Billed - _TIRC",
                    "debit": 1999.0,
                    "credit": 0.0,
                },
                {
                    "account": "Administrative Expenses - _TIRC",
                    "debit": 2677.64,
                    "credit": 0.0,
                },
                {
                    "account": "Cost of Goods Sold - _TIRC",
                    "debit": 267.26,  # stock with gst expense
                    "credit": 0.0,
                },
                {"account": "Creditors - _TIRC", "debit": 0.0, "credit": 5610.0},
            ],
        )

        self.assertStockValues(doc.name, {"Test Stock Item": None})

    @toggle_provisional_accounting()
    def test_purchase_receipt_and_then_purchase_invoice_for_provisional_expense(self):
        """
        No change in accounting because of provisional accounting as it's reversed on purchase invoice
        """
        transaction_details = {
            "doctype": "Purchase Receipt",
            "items": SAMPLE_ITEM_LIST,
            "is_in_state": 1,
        }

        doc = create_transaction(**transaction_details)

        self.assertGLEntry(
            doc.name,
            [
                {"account": "GST Expense - _TIRC", "debit": 0.0, "credit": 190.08},
                {
                    "account": "Asset Received But Not Billed - _TIRC",
                    "debit": 0.0,
                    "credit": 1999.0,
                },
                {
                    "account": "CWIP Account - _TIRC",
                    "debit": 2178.82,
                    "credit": 0.0,
                },
                {
                    "account": "Administrative Expenses - _TIRC",
                    "debit": 998.0,
                    "credit": 0.0,
                },
                {
                    "account": "Unsecured Loans - _TIRC",
                    "debit": 0.0,
                    "credit": 998.0,
                },
                {
                    "account": "Administrative Expenses - _TIRC",
                    "debit": 1500.0,
                    "credit": 0.0,
                },
                {
                    "account": "Unsecured Loans - _TIRC",
                    "debit": 0.0,
                    "credit": 1500.0,
                },
                {
                    "account": "Stock Received But Not Billed - _TIRC",
                    "debit": 0.0,
                    "credit": 257.0,
                },
                {
                    "account": "Stock In Hand - _TIRC",
                    "debit": 267.26,
                    "credit": 0.0,
                },
            ],
        )

        self.assertStockValues(
            doc.name, {"Test Stock Item": 20, "Test Ineligible Stock Item": 22.42}
        )

        self.assertAssetValues(
            "Purchase Receipt",
            doc.name,
            {"Test Fixed Asset": 1000, "Test Ineligible Fixed Asset": 1178.82},
        )

        # Create Purchase Invoice
        doc = make_purchase_invoice(doc.name)
        doc.bill_no = "BILL-07"
        doc.submit()

        self.assertEqual(doc.ineligibility_reason, "Ineligible As Per Section 17(5)")

        self.assertGLEntry(
            doc.name,
            [
                {"account": "Round Off - _TIRC", "debit": 0.28, "credit": 0.0},
                {
                    "account": "GST Expense - _TIRC",
                    "debit": 369.72,
                    "credit": 179.64,
                },
                {
                    "account": "Input Tax SGST - _TIRC",
                    "debit": 427.86,
                    "credit": 184.86,
                },
                {
                    "account": "Input Tax CGST - _TIRC",
                    "debit": 427.86,
                    "credit": 184.86,
                },
                {
                    "account": "Asset Received But Not Billed - _TIRC",
                    "debit": 1999.0,
                    "credit": 0.0,
                },
                {
                    "account": "Administrative Expenses - _TIRC",
                    "debit": 2677.64,
                    "credit": 0.0,
                },
                {
                    "account": "Stock Received But Not Billed - _TIRC",
                    "debit": 257.0,
                    "credit": 0.0,
                },
                {"account": "Creditors - _TIRC", "debit": 0.0, "credit": 5610.0},
            ],
        )

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_purchase_invoice_with_bill_of_entry(self):
        transaction_details = {
            "doctype": "Purchase Invoice",
            "supplier": "_Test Foreign Supplier",
            "bill_no": "BILL-08",
            "update_stock": 1,
            "items": SAMPLE_ITEM_LIST,
        }
        doc = create_transaction(**transaction_details)
        boe = make_bill_of_entry(doc.name)
        boe.bill_of_entry_no = "BILL-09"
        boe.bill_of_entry_date = today()
        boe.submit()

        self.assertGLEntry(
            boe.name,
            [
                {
                    "account": "Administrative Expenses - _TIRC",
                    "debit": 179.64,
                    "credit": 0.0,
                },
                {
                    "account": "Customs Duty Payable - _TIRC",
                    "debit": 0.0,
                    "credit": 855.72,
                },
                {"account": "GST Expense - _TIRC", "debit": 369.72, "credit": 179.64},
                {"account": "Input Tax IGST - _TIRC", "debit": 0.0, "credit": 369.72},
                {"account": "Input Tax IGST - _TIRC", "debit": 855.72, "credit": 0.0},
            ],
        )

        lcv = make_landed_cost_voucher(boe.name)
        lcv.save()

        for item in lcv.items:
            if item.item_code == "Test Ineligible Stock Item":
                self.assertEqual(item.applicable_charges, 3.42)  # 10.26 / 3 Nos
            elif item.item_code == "Test Ineligible Fixed Asset":
                self.assertEqual(item.applicable_charges, 179.82)
            else:
                self.assertEqual(item.applicable_charges, 0.0)

        for row in lcv.taxes:
            if row.expense_account == "GST Expense - _TIRC":
                self.assertEqual(row.amount, 190.08)
            else:
                self.assertEqual(row.amount, 0.0)

    def assertGLEntry(self, docname, expected_gl_entry):
        gl_entries = frappe.get_all(
            "GL Entry",
            filters={"voucher_no": docname},
            fields=["account", "debit", "credit"],
        )

        out_str = json.dumps(sorted(gl_entries, key=json.dumps))
        expected_out_str = json.dumps(sorted(expected_gl_entry, key=json.dumps))

        self.assertEqual(out_str, expected_out_str)

    def assertAssetValues(self, doctype, docname, asset_values):
        for asset, value in asset_values.items():
            asset_purchase_value = frappe.db.get_value(
                "Asset",
                {f"{frappe.scrub(doctype)}": docname, "item_code": asset},
                "gross_purchase_amount",
            )
            self.assertEqual(asset_purchase_value, value)

    def assertStockValues(self, docname, incoming_rates):
        for item, value in incoming_rates.items():
            incoming_rate = frappe.db.get_value(
                "Stock Ledger Entry",
                {"voucher_no": docname, "item_code": item},
                "incoming_rate",
            )
            self.assertEqual(incoming_rate, value)


def create_test_items():
    item_defaults = {
        "company": "_Test Indian Registered Company",
        "default_warehouse": "Stores - _TIRC",
        "expense_account": "Cost of Goods Sold - _TIRC",
        "buying_cost_center": "Main - _TIRC",
        "selling_cost_center": "Main - _TIRC",
        "income_account": "Sales - _TIRC",
    }

    stock_item = {
        "doctype": "Item",
        "item_code": "Test Stock Item",
        "item_group": "All Item Groups",
        "gst_hsn_code": "730419",
        "is_stock_item": 1,
        "item_defaults": [item_defaults],
    }

    asset_account = frappe.get_doc(
        {
            "doctype": "Account",
            "account_name": "Asset Account",
            "parent_account": "Fixed Assets - _TIRC",
            "account_type": "Fixed Asset",
        }
    )
    asset_account.insert()

    asset_category = frappe.get_doc(
        {
            "doctype": "Asset Category",
            "asset_category_name": "Test Asset Category",
            # TODO: Ensure same accounting for without cwip after ERPNext PR 37542 is merged
            "enable_cwip_accounting": 1,
            "accounts": [
                {
                    "company_name": "_Test Indian Registered Company",
                    "fixed_asset_account": asset_account.name,
                    "capital_work_in_progress_account": "CWIP Account - _TIRC",
                }
            ],
        }
    )
    asset_category.insert()

    frappe.get_doc({"doctype": "Location", "location_name": "Test Location"}).insert()

    asset_item = {
        "doctype": "Item",
        "item_code": "Test Fixed Asset",
        "item_group": "All Item Groups",
        "gst_hsn_code": "730419",
        "is_stock_item": 0,
        "is_fixed_asset": 1,
        "auto_create_assets": 1,
        "asset_category": asset_category.name,
        "asset_naming_series": "ACC-ASS-.YYYY.-",
        "item_defaults": [item_defaults],
    }

    service_item = {
        "doctype": "Item",
        "item_code": "Test Service Item",
        "item_group": "All Item Groups",
        "gst_hsn_code": "730419",
        "is_stock_item": 0,
        "item_defaults": [
            {**item_defaults, "expense_account": "Administrative Expenses - _TIRC"}
        ],
    }

    # Stock Item
    frappe.get_doc(stock_item).insert()
    frappe.get_doc(
        {
            **stock_item,
            "item_code": "Test Ineligible Stock Item",
            "is_ineligible_for_itc": 1,
        }
    ).insert()

    # Fixed Asset
    frappe.get_doc(asset_item).insert()
    frappe.get_doc(
        {
            **asset_item,
            "item_code": "Test Ineligible Fixed Asset",
            "is_ineligible_for_itc": 1,
        }
    ).insert()

    # Service Item
    frappe.get_doc(service_item).insert()
    frappe.get_doc(
        {
            **service_item,
            "item_code": "Test Ineligible Service Item",
            "is_ineligible_for_itc": 1,
        }
    ).insert()
