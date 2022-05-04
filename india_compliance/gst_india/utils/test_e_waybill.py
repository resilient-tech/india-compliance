import unittest

import frappe

from india_compliance.gst_india.utils.e_waybill import (
    cancel_e_waybill,
    generate_e_waybill,
    update_transporter,
    update_vehicle_info,
)
from india_compliance.gst_india.utils.test_e_invoice import create_sales_invoice


class TestEWaybill(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        frappe.db.set_single_value("GST Settings", "enable_e_invoice", 0)

    @classmethod
    def tearDownClass(self):
        pass

    def test_generate_e_waybill(self):
        si = create_sales_invoice(
            naming_series="SINV-.CFY.-",
            item_code="Test Sample",
            item_name="Test Sample",
            gst_hsn_code="73041990",
            do_not_submit=True,
        )
        si.gst_category = "Registered Regular"
        si.save()
        si.submit()

        values = {
            "transporter": "_Test Common Supplier",
            "distance": 10,
            "mode_of_transport": "Road",
            "vehicle_no": "GJ07DL9009",
        }

        generate_e_waybill(doctype=si.doctype, docname=si.name, values=values)

        transporter_values = {
            "transporter": "_Test Common Supplier",
            "gst_transporter_id": "29AKLPM8755F1Z2",
            "update_e_waybill_data": 1,
        }
        update_transporter(
            doctype=si.doctype, docname=si.name, values=transporter_values
        )

        vehicle_info = frappe._dict(
            {
                "vehicle_no": "GJ07DL9009",
                "mode_of_transport": "Road",
                "gst_vehicle_type": "Regular",
                "reason": "Others",
                "remark": "Vehicle Type added",
                "update_e_waybill_data": 1,
            }
        )
        update_vehicle_info(doctype=si.doctype, docname=si.name, values=vehicle_info)

        values = {"reason": "Data Entry Mistake", "remark": "For Test"}
        cancel_e_waybill(doctype=si.doctype, docname=si.name, values=values)
