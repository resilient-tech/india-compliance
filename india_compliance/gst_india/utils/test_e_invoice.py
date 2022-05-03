import unittest

import frappe
from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import (
    create_sales_invoice,
)
from erpnext.buying.doctype.supplier.test_supplier import create_supplier

from india_compliance.gst_india.utils.e_invoice import (
    cancel_e_invoice,
    generate_e_invoice,
)
from india_compliance.gst_india.utils.e_waybill import generate_e_waybill


class TestEInvoice(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        si = create_sales_invoice(
            naming_series="SINV-.CFY.-", item_code="Test Sample", do_not_submit=True
        )
        si.gst_category = "Registered Regular"
        si.save()
        si.submit()
        self.sales_invoice = si

    @classmethod
    def tearDownClass(self):
        pass

    def test_generate_irn(self):
        generate_e_invoice(self.sales_invoice.name)
        irn = frappe.db.get_value("Sales Invoice", self.sales_invoice.name, "irn")
        e_invoice_log = frappe.db.get_value(
            "e-Invoice Log", {"sales_invoice": self.sales_invoice.name}, "name"
        )
        self.assertEqual(irn, e_invoice_log)

        self._generate_e_waybill()

        values = {"reason": "Others", "remark": "Test"}
        cancel_e_invoice(self.sales_invoice.name, values)

    def _generate_e_waybill(self):
        supplier = create_supplier(
            supplier_name="_Test Common Supplier",
            supplier_group="Unregistered Supplier",
        )
        supplier.is_transporter = True
        supplier.save()

        values = {
            "transporter": supplier.name,
            "distance": 0,
            "mode_of_transport": "Road",
            "vehicle_no": "GJ07DL9009",
        }

        generate_e_waybill(
            doctype=self.sales_invoice.doctype,
            docname=self.sales_invoice.name,
            values=values,
        )
        ewaybill = frappe.db.get_value(
            "Sales Invoice", self.sales_invoice.name, "ewaybill"
        )
        e_waybill_log = frappe.db.get_value(
            "e-Waybill Log", {"reference_name": self.sales_invoice.name}, "name"
        )
        self.assertEqual(ewaybill, e_waybill_log)
