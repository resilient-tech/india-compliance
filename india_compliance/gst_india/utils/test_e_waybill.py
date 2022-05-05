import json
import unittest

import frappe
from frappe import _

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
        frappe.db.set_single_value("GST Settings", "enable_e_waybill", 1)
        frappe.db.set_single_value("GST Settings", "auto_generate_e_waybill", 0)

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
        frappe.db.set_single_value("GST Settings", "enable_e_waybill", 0)
        frappe.db.set_single_value("GST Settings", "auto_generate_e_waybill", 1)

    def test_generate_e_waybill(self):
        self._generate_e_waybill()
        self._update_transporter()
        self._update_vehicle_info()
        self._cancel_e_waybill()

    def _generate_e_waybill(self):
        values = {
            "transporter": "_Test Common Supplier",
            "distance": 10,
            "mode_of_transport": "Road",
            "vehicle_no": "GJ07DL9009",
        }

        generate_e_waybill(doctype=self.si.doctype, docname=self.si.name, values=values)

        expected_result = "E-Way Bill is generated successfully"

        integration_request = frappe.get_last_doc("Integration Request")
        self.assertEqual(
            expected_result, json.loads(integration_request.output).get("message")
        )

    def _update_transporter(self):
        transporter_values = {
            "transporter": "_Test Common Supplier",
            "gst_transporter_id": "29AKLPM8755F1Z2",
            "update_e_waybill_data": 1,
        }
        update_transporter(
            doctype=self.si.doctype, docname=self.si.name, values=transporter_values
        )

        expected_comment = (
            "Transporter Info has been updated by {user}. New Transporter ID is"
            " {transporter_id}."
        ).format(
            user=frappe.bold(frappe.utils.get_fullname()),
            transporter_id=frappe.bold(transporter_values["gst_transporter_id"]),
        )

        comment = frappe.get_last_doc("Comment")
        self.assertEqual(expected_comment, comment.content)

    def _update_vehicle_info(self):
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
        update_vehicle_info(
            doctype=self.si.doctype, docname=self.si.name, values=vehicle_info
        )

        values_in_comment = {
            "Vehicle No": vehicle_info.vehicle_no,
            "LR No": vehicle_info.lr_no,
            "LR Date": vehicle_info.lr_date,
            "Mode of Transport": vehicle_info.mode_of_transport,
            "GST Vehicle Type": vehicle_info.gst_vehicle_type,
        }

        expected_comment = (
            "Vehicle Info has been updated by {user}.<br><br> New details are: <br>"
        ).format(user=frappe.bold(frappe.utils.get_fullname()))

        for key, value in values_in_comment.items():
            if value:
                expected_comment += "{0}: {1} <br>".format(frappe.bold(_(key)), value)

        comment = frappe.get_last_doc("Comment")
        self.assertEqual(expected_comment, comment.content)

    def _cancel_e_waybill(self):
        values = {"reason": "Data Entry Mistake", "remark": "For Test"}
        cancel_e_waybill(doctype=self.si.doctype, docname=self.si.name, values=values)

        expected_result = "E-Way Bill is cancelled successfully"

        integration_request = frappe.get_last_doc("Integration Request")
        self.assertEqual(
            expected_result, json.loads(integration_request.output).get("message")
        )
