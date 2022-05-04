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
