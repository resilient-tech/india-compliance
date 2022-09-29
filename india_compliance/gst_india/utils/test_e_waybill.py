import json
import re

import requests
import responses
from responses import matchers

import frappe
from frappe import _
from frappe.tests.utils import FrappeTestCase

from india_compliance.gst_india.api_classes import EWaybillAPI
from india_compliance.gst_india.utils.e_waybill import (
    EWaybillData,
    cancel_e_waybill,
    log_and_process_e_waybill_generation,
    update_transporter,
    update_vehicle_info,
)
from india_compliance.gst_india.utils.tests import create_sales_invoice

# from frappe.utils import add_to_date, getdate, now_datetime, today
# from frappe.utils.data import format_date


class TestEWaybill(FrappeTestCase):
    BASE_URL = "https://asp.resilient.tech"

    @classmethod
    def setUpClass(cls):
        frappe.db.set_value(
            "GST Settings",
            "GST Settings",
            {
                "enable_api": 1,
                "enable_e_invoice": 0,
                "auto_generate_e_invoice": 0,
                "enable_e_waybill": 1,
                "fetch_e_waybill_data": 0,
                "auto_generate_e_waybill": 0,
            },
        )
        cls.e_waybill_test_data = frappe.get_file_json(
            frappe.get_app_path("india_compliance", "tests", "e_waybill_test_data.json")
        )

    @classmethod
    def tearDownClass(cls):
        frappe.db.set_value(
            "GST Settings",
            "GST Settings",
            {
                "enable_api": 0,
                "enable_e_invoice": 0,
                "auto_generate_e_invoice": 1,
                "enable_e_waybill": 0,
                "fetch_e_waybill_data": 1,
            },
        )
        frappe.db.rollback()

    @responses.activate
    def test_validate_transaction(self):
        test_data = self.e_waybill_test_data.get("goods_item_with_ewaybill")
        test_data.get("kwargs").update(
            {
                "transporter": "_Test Common Supplier",
                "distance": 10,
                "mode_of_transport": "Road",
            }
        )
        si = create_sales_invoice(**test_data.get("kwargs"))

        result = self._mock_e_waybill_response(si, test_data)
        si.ewaybill = result.ewayBillNo

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(e-Waybill already generated.*)$"),
            EWaybillData(si).validate_transaction,
        )

    def test_validate_applicability(self):
        test_data = self.e_waybill_test_data.get("goods_item_with_ewaybill")
        test_data.get("kwargs").update({"customer_address": ""})
        si = create_sales_invoice(**test_data.get("kwargs"))

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(.*is required to generate e-Waybill)$"),
            EWaybillData(si).validate_applicability,
        )

    @responses.activate
    def test_generate_e_waybill(self):
        test_data = self.e_waybill_test_data.get("goods_item_with_ewaybill")
        test_data.get("kwargs").update(
            {
                "transporter": "_Test Common Supplier",
                "distance": 10,
                "mode_of_transport": "Road",
            }
        )
        si = create_sales_invoice(**test_data.get("kwargs"))

        result = self._mock_e_waybill_response(si, test_data)

        log_and_process_e_waybill_generation(si, result)

        self.assertDocumentEqual(
            {"name": result.ewayBillNo},
            frappe.get_doc("e-Waybill Log", {"reference_name": si.name}),
        )

    def _mock_e_waybill_response(self, doc, data):
        request_data = EWaybillData(doc).get_data()

        responses.add(
            responses.POST,
            self.BASE_URL + "/test/ewb/ewayapi",
            body=json.dumps(data.get("response_data")),
            match=[
                matchers.query_param_matcher(data.get("params")),
                matchers.json_params_matcher(request_data),
            ],
            status=200,
        )

        eway_api = EWaybillAPI(doc)
        eway_api.default_headers.update({"requestid": frappe.generate_hash(length=12)})

        response = requests.post(
            self.BASE_URL + "/test/ewb/ewayapi",
            headers=eway_api.default_headers,
            params=data.get("params"),
            json=request_data,
        )

        response_json = response.json(object_hook=frappe._dict)
        return response_json.get("result", response_json)

    def test_update_transporter(self):
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

    # def update_test_data(self, test_data, values=None):
    #     response_data = test_data.get("response_data")

    #     today_date = format_date(today(), "dd/mm/yyyy")

    #     # request_data.update({"docDate": today_date})

    #     current_datetime = now_datetime().strftime("%d/%m/%Y %I:%M:%S %p")
    #     next_day_datetime = add_to_date(getdate(), days=1).strftime(
    #         "%d/%m/%Y %I:%M:%S %p"
    #     )

    #     response_data.get("result").update(
    #         {"ewayBillDate": current_datetime, "validUpto": next_day_datetime}
    #     )
