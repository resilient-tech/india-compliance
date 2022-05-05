import json
import unittest

import frappe
from frappe.utils import nowdate
from erpnext.buying.doctype.supplier.test_supplier import create_supplier

from india_compliance.gst_india.utils.e_invoice import (
    cancel_e_invoice,
    generate_e_invoice,
)
from india_compliance.gst_india.utils.e_waybill import generate_e_waybill


class TestEInvoice(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        frappe.db.set_single_value("GST Settings", "enable_e_invoice", 1)
        frappe.db.set_single_value("GST Settings", "auto_generate_e_invoice", 0)
        frappe.db.set_single_value("GST Settings", "enable_e_waybill", 1)

        self.si = create_sales_invoice(
            item_code="Test Sample",
            item_name="Test Sample",
            gst_hsn_code="73041990",
            do_not_submit=True,
        )
        self.si.gst_category = "Registered Regular"
        self.si.save()
        self.si.submit()

    @classmethod
    def tearDownClass(self):
        frappe.db.set_single_value("GST Settings", "enable_e_invoice", 0)
        frappe.db.set_single_value("GST Settings", "auto_generate_e_invoice", 1)

    def test_generate_irn(self):
        generate_e_invoice(self.si.name)

        expected_result = "IRN generated successfully"
        integration_request = frappe.get_last_doc("Integration Request")
        self.assertEqual(
            expected_result, json.loads(integration_request.output).get("message")
        )

        self._generate_e_waybill()
        self._cancel_e_invoice()

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
            doctype=self.si.doctype,
            docname=self.si.name,
            values=values,
        )
        expected_result = "E-Way Bill generated successfully"

        integration_request = frappe.get_last_doc("Integration Request")
        self.assertEqual(
            expected_result, json.loads(integration_request.output).get("message")
        )

    def _cancel_e_invoice(self):
        values = {"reason": "Others", "remark": "Test"}
        cancel_e_invoice(self.si.name, values)

        expected_result = "E-Invoice is cancelled successfully"

        integration_request = frappe.get_last_doc("Integration Request")
        self.assertEqual(
            expected_result, json.loads(integration_request.output).get("message")
        )


def create_sales_invoice(**args):
    si = frappe.new_doc("Sales Invoice")
    args = frappe._dict(args)
    if args.posting_date:
        si.set_posting_time = 1
    si.posting_date = args.posting_date or nowdate()

    si.company = args.company or "_Test Company"
    si.customer = args.customer or "_Test Customer"
    si.debit_to = args.debit_to or "Debtors - _TC"
    si.update_stock = args.update_stock
    si.is_pos = args.is_pos
    si.is_return = args.is_return
    si.return_against = args.return_against
    si.currency = args.currency or "INR"
    si.conversion_rate = args.conversion_rate or 1
    si.naming_series = args.naming_series or "T-SINV-"
    si.cost_center = args.parent_cost_center

    si.append(
        "items",
        {
            "item_code": args.item or args.item_code or "_Test Item",
            "item_name": args.item_name or "_Test Item",
            "description": args.description or "_Test Item",
            "gst_hsn_code": args.gst_hsn_code or "999800",
            "warehouse": args.warehouse or "_Test Warehouse - _TC",
            "qty": args.qty or 1,
            "uom": args.uom or "Nos",
            "stock_uom": args.uom or "Nos",
            "rate": args.rate if args.get("rate") is not None else 100,
            "price_list_rate": args.price_list_rate
            if args.get("price_list_rate") is not None
            else 100,
            "income_account": args.income_account or "Sales - _TC",
            "expense_account": args.expense_account or "Cost of Goods Sold - _TC",
            "discount_account": args.discount_account or None,
            "discount_amount": args.discount_amount or 0,
            "asset": args.asset or None,
            "cost_center": args.cost_center or "_Test Cost Center - _TC",
            "serial_no": args.serial_no,
            "conversion_factor": 1,
            "incoming_rate": args.incoming_rate or 0,
        },
    )

    if not args.do_not_save:
        si.insert()
        if not args.do_not_submit:
            si.submit()
        else:
            si.payment_schedule = []
    else:
        si.payment_schedule = []

    return si
