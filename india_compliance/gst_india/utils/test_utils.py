import unittest
from unittest.mock import patch

import frappe
from erpnext.selling.doctype.sales_order.sales_order import (
    make_delivery_note,
    make_sales_invoice,
)
from erpnext.selling.doctype.sales_order.test_sales_order import make_sales_order
from erpnext.stock.doctype.item.test_item import make_item
from erpnext.stock.doctype.warehouse.test_warehouse import create_warehouse

from india_compliance.gst_india.overrides.item import (
    validate_hsn_code as validate_item_hsn_code,
)
from india_compliance.gst_india.overrides.sales_invoice import validate_document_name
from india_compliance.gst_india.overrides.transaction import validate_hsn_code


class TestUtils(unittest.TestCase):
    @patch("frappe.get_cached_value")
    def test_validate_document_name(self, mock_get_cached):
        mock_get_cached.return_value = "India"  # mock country
        posting_date = "2021-05-01"

        invalid_names = [
            "SI$1231",
            "012345678901234567",
            "SI 2020 05",
            "SI.2020.0001",
            "PI2021 - 001",
        ]
        for name in invalid_names:
            doc = frappe._dict(name=name, posting_date=posting_date)
            self.assertRaises(frappe.ValidationError, validate_document_name, doc)

        valid_names = [
            "012345678901236",
            "SI/2020/0001",
            "SI/2020-0001",
            "2020-PI-0001",
            "PI2020-0001",
        ]
        for name in valid_names:
            doc = frappe._dict(name=name, posting_date=posting_date)
            try:
                validate_document_name(doc)
            except frappe.ValidationError:
                self.fail("Valid name {} throwing error".format(name))

    @patch("frappe.get_cached_value")
    def test_validate_document_name_not_india(self, mock_get_cached):
        mock_get_cached.return_value = "Not India"
        doc = frappe._dict(name="SI$123", posting_date="2021-05-01")

        try:
            validate_document_name(doc)
        except frappe.ValidationError:
            self.fail(
                "Regional validation related to India are being applied to other countries"
            )

    def test_validate_item_hsn_code(self):
        # Validate GST HSN Code of Item Master
        item_doc = make_item("Test Sample")

        item_doc.gst_hsn_code = None or ""
        self.assertRaises(frappe.ValidationError, validate_item_hsn_code, item_doc)

        item_doc.gst_hsn_code = "5634"
        self.assertRaises(frappe.ValidationError, validate_item_hsn_code, item_doc)

    def test_validate_transaction_docs_hsn_code(self):
        # Create Test Customer if not exists
        if not frappe.db.exists("Customer", "Test Customer"):
            frappe.get_doc(
                {"doctype": "Customer", "customer_name": "Test Customer"}
            ).insert()

        # Create Test Warehouse if not exists
        warehouse = create_warehouse(
            "_Test Warehouse - _TC",
            {
                "company": "_Test Company",
                "parent_warehouse": "All Warehouses - _TC",
            },
        )

        # Validate GST HSN Code in transaction doctypes
        so = make_sales_order(
            customer="Test Customer",
            warehouse=warehouse,
            item="Test Sample",
            do_not_submit=True,
        )

        self.validate_transaction_doc(so)
        so.submit()

        si = make_sales_invoice(so.name)
        si.insert()
        self.validate_transaction_doc(si)

        dn = make_delivery_note(so.name)
        dn.insert()
        self.validate_transaction_doc(dn)

    def validate_transaction_doc(self, doc):
        test_item_hsn_code = frappe.db.get_value("Item", "Test Sample", "gst_hsn_code")

        doc.get("items")[0].gst_hsn_code = "5632"
        self.assertRaises(frappe.ValidationError, validate_hsn_code, doc)
        doc.get("items")[0].gst_hsn_code = test_item_hsn_code
