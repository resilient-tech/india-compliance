import json
import re

import responses
from responses import matchers

import frappe
from frappe.tests.utils import FrappeTestCase, change_settings
from frappe.utils import add_to_date, getdate, now_datetime, today
from frappe.utils.data import format_date

from india_compliance.gst_india.utils.e_waybill import (
    EWaybillData,
    cancel_e_waybill,
    fetch_e_waybill_data,
    generate_e_waybill,
    update_transporter,
    update_vehicle_info,
)
from india_compliance.gst_india.utils.tests import create_sales_invoice


class TestEWaybill(FrappeTestCase):
    BASE_URL = "https://asp.resilient.tech"

    today_date = format_date(today(), "dd/mm/yyyy")
    current_datetime = now_datetime().strftime("%d/%m/%Y %I:%M:%S %p")
    next_day_datetime = add_to_date(getdate(), days=1).strftime("%d/%m/%Y %I:%M:%S %p")
    before_day = add_to_date(getdate(), days=-2).strftime("%d/%m/%Y %I:%M:%S %p")

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
                "fetch_e_waybill_data": 1,
                "auto_generate_e_waybill": 0,
                "attach_e_waybill_print": 1,
            },
        )
        cls.e_waybill_test_data = frappe.get_file_json(
            frappe.get_app_path("india_compliance", "tests", "e_waybill_test_data.json")
        )

        cls.si, cls._test_data = _create_sales_invoice(
            cls.e_waybill_test_data.get("goods_item_with_ewaybill"),
            cls.current_datetime,
            cls.next_day_datetime,
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
                "attach_e_waybill_print": 1,
            },
        )
        frappe.db.rollback()

    @responses.activate
    def test_generate_e_waybill(self):
        """Tetst generate_e_waybill whitelisted method"""
        # Use of common function to generate e_waybill
        self._generate_e_waybill()

        self.assertDocumentEqual(
            {
                "name": self._test_data.get("response_data")
                .get("result")
                .get("ewayBillNo")
            },
            frappe.get_doc("e-Waybill Log", {"reference_name": self.si.name}),
        )

    @responses.activate
    def test_update_vehicle_info(self):
        """Test whitelisted function `update_vehicle_info`"""
        self._generate_e_waybill()

        # get test data from test json and update date accordingly
        test_data = self.e_waybill_test_data.get("update_vehicle_info")
        test_data.get("response_data").get("result").update(
            {"vehUpdDate": self.current_datetime, "validUpto": self.next_day_datetime}
        )

        # values required to update vehicle info
        vehicle_info = frappe._dict(
            {
                "vehicle_no": "GJ07DL9001",
                "mode_of_transport": "Road",
                "gst_vehicle_type": "Regular",
                "reason": "Others",
                "remark": "Vehicle Info added",
                "update_e_waybill_data": 1,
            }
        )
        request_data = test_data.get("request_data")

        # Mock API response of VEHEWB to update vehicle info
        self._mock_e_waybill_response(
            data=test_data,
            match_list=[
                matchers.query_param_matcher(test_data.get("params")),
                matchers.json_params_matcher(request_data),
            ],
        )

        # Mock get_e_waybill response
        self._mock_fetch_e_waybill_response()

        update_vehicle_info(
            doctype="Sales Invoice", docname=self.si.name, values=vehicle_info
        )

        # assertions
        expected_comment = "Vehicle Info has been updated by <strong>Administrator</strong>.<br><br> New details are: <br><strong>Vehicle No</strong>: GJ07DL9001 <br><strong>Mode of Transport</strong>: Road <br><strong>GST Vehicle Type</strong>: Regular <br>"

        self.assertDocumentEqual(
            {"name": request_data.get("ewbNo")},
            frappe.get_doc("e-Waybill Log", {"reference_name": self.si.name}),
        )

        self.assertDocumentEqual(
            {
                "reference_doctype": "e-Waybill Log",
                "reference_name": request_data.get("ewbNo"),
                "content": expected_comment,
            },
            frappe.get_doc("Comment", {"reference_name": request_data.get("ewbNo")}),
        )

    @responses.activate
    def test_update_transporter(self):
        """Test whitelisted method `update_transporter`"""
        self._generate_e_waybill()

        # get test data from test json and update date accordingly
        test_data = self.e_waybill_test_data.get("update_transporter")
        test_data.get("response_data").get("result").update(
            {"transUpdateDate": self.current_datetime}
        )

        # transporter values to update transporter
        transporter_values = frappe._dict(
            {
                "transporter": "_Test Common Supplier",
                "gst_transporter_id": "05AAACG2140A1ZL",
            }
        )

        request_data = test_data.get("request_data")

        # Mock response for UPDATETRANSPORTER
        self._mock_e_waybill_response(
            data=test_data,
            match_list=[
                matchers.query_param_matcher(test_data.get("params")),
                matchers.json_params_matcher(request_data),
            ],
        )

        update_transporter(
            doctype="Sales Invoice",
            docname=self.si.name,
            values=transporter_values,
        )

        # assertions
        self.assertDocumentEqual(
            {"name": request_data.get("ewbNo")},
            frappe.get_doc("e-Waybill Log", {"reference_name": self.si.name}),
        )

        self.assertDocumentEqual(
            {
                "reference_doctype": "e-Waybill Log",
                "reference_name": request_data.get("ewbNo"),
                "content": "Transporter Info has been updated by <strong>Administrator</strong>. New Transporter ID is <strong>05AAACG2140A1ZL</strong>.",
            },
            frappe.get_doc("Comment", {"reference_name": request_data.get("ewbNo")}),
        )

    @change_settings(
        "GST Settings", {"fetch_e_waybill_data": 0, "attach_e_waybill_print": 0}
    )
    @responses.activate
    def test_fetch_e_waybill_data(self):
        """Test e-Waybill Print and Attach Functions"""
        self._generate_e_waybill()
        self._mock_fetch_e_waybill_response()

        fetch_e_waybill_data(doctype="Sales Invoice", docname=self.si.name, attach=True)

        self.assertTrue(
            frappe.get_doc(
                "File",
                {
                    "attached_to_doctype": "Sales Invoice",
                    "attached_to_name": self.si.name,
                },
            )
        )

    @responses.activate
    def test_cancel_e_waybill(self):
        """Test cancel_e_waybill"""

        self._generate_e_waybill()

        # test data to mock cancel e_waybill response
        test_data = self.e_waybill_test_data.get("cancel_e_waybill")
        test_data.get("response_data").get("result").update(
            {"cancelDate": self.current_datetime}
        )

        # values required to cancel e_waybill
        values = frappe._dict({"reason": "Data Entry Mistake", "remark": "For Test"})

        # Mock response for CANEWB
        self._mock_e_waybill_response(
            data=self.e_waybill_test_data.get("cancel_e_waybill"),
            match_list=[
                matchers.query_param_matcher(test_data.get("params")),
                matchers.json_params_matcher(test_data.get("request_data")),
            ],
        )

        cancel_e_waybill(doctype=self.si.doctype, docname=self.si.name, values=values)

        # assertions
        self.assertTrue(
            frappe.get_doc(
                "e-Waybill Log", {"reference_name": self.si.name, "is_cancelled": 1}
            )
        )

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
        self.si = create_sales_invoice(**test_data.get("kwargs"))

        self.si.ewaybill = (
            test_data.get("response_data").get("result").get("ewayBillNo")
        )

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(e-Waybill already generated.*)$"),
            EWaybillData(self.si).validate_transaction,
        )

    def test_validate_applicability(self):
        test_data = self.e_waybill_test_data.get("goods_item_with_ewaybill")
        test_data.get("kwargs").update({"customer_address": ""})
        self.si = create_sales_invoice(**test_data.get("kwargs"))

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(.*is required to generate e-Waybill)$"),
            EWaybillData(self.si).validate_applicability,
        )

    # helper functions
    def _generate_e_waybill(self):
        # Update docNo and docDate in request data as per sales invoice
        self._test_data.get("request_data").update(
            {"docNo": "53amoi", "docDate": self.today_date}
        )

        # Mock POST response for generate_e_waybill
        self._mock_e_waybill_response(
            data=self._test_data,
            match_list=[
                matchers.query_param_matcher(self._test_data.get("params")),
                matchers.json_params_matcher(self._test_data.get("request_data")),
            ],
        )

        # Mock GET response for get_e_waybill
        self._mock_fetch_e_waybill_response()

        generate_e_waybill(
            doctype="Sales Invoice",
            docname=self.si.name,
        )

    def _mock_fetch_e_waybill_response(self):
        get_e_waybill_test_data = self.e_waybill_test_data.get("get_e_waybill")
        request_data = get_e_waybill_test_data.get("request_data")

        for data in (
            get_e_waybill_test_data.get("response_data")
            .get("result")
            .get("VehiclListDetails")
        ):
            data["enteredDate"] = self.current_datetime

        get_e_waybill_test_data.get("response_data").update(
            {
                "docDate": self.today_date,
                "ewayBillDate": self.current_datetime,
                "validUpto": self.next_day_datetime,
            }
        )

        self._mock_e_waybill_response(
            data=get_e_waybill_test_data,
            match_list=[
                matchers.query_param_matcher(request_data),
            ],
            method="GET",
            api="getewaybill",
        )

    def _mock_e_waybill_response(self, data, match_list, method="POST", api=None):
        api_path = "/test/ewb/ewayapi/"

        if api:
            api_path = f"{api_path}{api}"

        if method == "GET":
            responses.add(
                responses.GET,
                self.BASE_URL + api_path,
                body=json.dumps(data.get("response_data")),
                match=match_list,
                status=200,
            )
        elif method == "POST":
            responses.add(
                responses.POST,
                self.BASE_URL + api_path,
                body=json.dumps(data.get("response_data")),
                match=match_list,
                status=200,
            )

    def update_test_data(self, test_data, update_vehicle_info=False):
        response_data = test_data.get("response_data")

        current_datetime = now_datetime().strftime("%d/%m/%Y %I:%M:%S %p")
        next_day_datetime = add_to_date(getdate(), days=1).strftime(
            "%d/%m/%Y %I:%M:%S %p"
        )

        response_data.get("result").update({"ewayBillDate": current_datetime})

        if update_vehicle_info:
            response_data.get("result").update(
                {"ewayBillDate": current_datetime, "validUpto": next_day_datetime}
            )


def _create_sales_invoice(invoice_data, current_datetime, next_day_datetime):
    """Generate Sales Invoice to test e-Waybill functionalities"""
    # update kwargs to process invoice
    invoice_data.get("kwargs").update(
        {
            "transporter": "_Test Common Supplier",
            "distance": 10,
            "mode_of_transport": "Road",
        }
    )

    # set date and time in mocked response data according to the api response
    invoice_data.get("response_data").get("result").update(
        {"ewayBillDate": current_datetime, "validUpto": next_day_datetime}
    )

    si = create_sales_invoice(**invoice_data.get("kwargs"), do_not_submit=True)
    si.gst_transporter_id = ""
    si.submit()
    return si, invoice_data
