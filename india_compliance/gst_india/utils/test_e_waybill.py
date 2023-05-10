import random
import re

import responses
from responses import matchers

import frappe
from frappe.tests.utils import FrappeTestCase, change_settings
from frappe.utils import add_to_date, get_datetime, getdate, now_datetime, today
from frappe.utils.data import format_date

from india_compliance.gst_india.api_classes.base import BASE_URL
from india_compliance.gst_india.utils import load_doc
from india_compliance.gst_india.utils.e_waybill import (
    EWaybillData,
    cancel_e_waybill,
    fetch_e_waybill_data,
    generate_e_waybill,
    update_transporter,
    update_vehicle_info,
)
from india_compliance.gst_india.utils.tests import (
    append_item,
    create_purchase_invoice,
    create_sales_invoice,
)

DATETIME_FORMAT = "%d/%m/%Y %I:%M:%S %p"
DATE_FORMAT = "dd/mm/yyyy"


class TestEWaybill(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        frappe.db.set_single_value(
            "GST Settings",
            {
                "enable_api": 1,
                "enable_e_invoice": 0,
                "auto_generate_e_invoice": 0,
                "enable_e_waybill": 1,
                "fetch_e_waybill_data": 0,
                "auto_generate_e_waybill": 0,
                "attach_e_waybill_print": 0,
            },
        )

        cls.e_waybill_test_data = frappe._dict(
            frappe.get_file_json(
                frappe.get_app_path(
                    "india_compliance", "gst_india", "data", "test_e_waybill.json"
                )
            )
        )

        cls.sales_invoice = _create_sales_invoice(cls.e_waybill_test_data)

    @classmethod
    def tearDownClass(cls):
        frappe.db.set_single_value(
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

    @classmethod
    def setUp(cls):
        update_dates_for_test_data(cls.e_waybill_test_data)

    def test_get_data(self):
        e_waybill_data = EWaybillData(self.sales_invoice).get_data()
        test_data = self.e_waybill_test_data.goods_item_with_ewaybill.get(
            "request_data"
        )

        self.assertDictContainsSubset(
            e_waybill_data,
            test_data,
        )

    @change_settings(
        "GST Settings", {"fetch_e_waybill_data": 1, "attach_e_waybill_print": 1}
    )
    @responses.activate
    def test_generate_e_waybill(self):
        """Test whitelisted method `generate_e_waybill`"""
        self._generate_e_waybill()

        self.assertDocumentEqual(
            {
                "name": self.e_waybill_test_data.goods_item_with_ewaybill.get(
                    "response_data"
                )
                .get("result")
                .get("ewayBillNo")
            },
            frappe.get_doc(
                "e-Waybill Log", {"reference_name": self.sales_invoice.name}
            ),
        )

    @responses.activate
    def test_update_vehicle_info(self):
        """Test whitelisted function `update_vehicle_info`"""
        self._generate_e_waybill()

        # get test data from test json and update date accordingly
        vehicle_data = self.e_waybill_test_data.get("update_vehicle_info")

        # Mock API response of VEHEWB to update vehicle info
        self._mock_e_waybill_response(
            data=vehicle_data.get("response_data"),
            match_list=[
                matchers.query_string_matcher(vehicle_data.get("params")),
                matchers.json_params_matcher(vehicle_data.get("request_data")),
            ],
        )

        update_vehicle_info(
            doctype="Sales Invoice",
            docname=self.sales_invoice.name,
            values=frappe._dict(vehicle_data.get("values")),
        )

        # assertions
        expected_comment = "Vehicle Info has been updated by <strong>Administrator</strong>.<br><br> New details are: <br><strong>Vehicle No</strong>: GJ07DL9001 <br><strong>Mode of Transport</strong>: Road <br><strong>GST Vehicle Type</strong>: Regular <br>"

        self.assertDocumentEqual(
            {"name": vehicle_data.get("request_data").get("ewbNo")},
            frappe.get_doc(
                "e-Waybill Log", {"reference_name": self.sales_invoice.name}
            ),
        )

        self.assertDocumentEqual(
            {
                "reference_doctype": "e-Waybill Log",
                "reference_name": vehicle_data.get("request_data").get("ewbNo"),
                "content": expected_comment,
            },
            frappe.get_doc(
                "Comment",
                {"reference_name": vehicle_data.get("request_data").get("ewbNo")},
            ),
        )

    @responses.activate
    def test_update_transporter(self):
        """Test whitelisted method `update_transporter`"""
        self._generate_e_waybill()

        # get test data from test json and update date accordingly
        test_data = self.e_waybill_test_data.get("update_transporter")

        # transporter values to update transporter
        transporter_values = frappe._dict(
            self.e_waybill_test_data.get("transporter_values")
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
            docname=self.sales_invoice.name,
            values=transporter_values,
        )

        # assertions
        self.assertDocumentEqual(
            {"name": request_data.get("ewbNo")},
            frappe.get_doc(
                "e-Waybill Log", {"reference_name": self.sales_invoice.name}
            ),
        )

        self.assertDocumentEqual(
            {
                "reference_doctype": "e-Waybill Log",
                "reference_name": request_data.get("ewbNo"),
                "content": "Transporter Info has been updated by <strong>Administrator</strong>. New Transporter ID is <strong>05AAACG2140A1ZL</strong>.",
            },
            frappe.get_doc("Comment", {"reference_name": request_data.get("ewbNo")}),
        )

    @responses.activate
    def _test_fetch_e_waybill_data(self):
        """Test e-Waybill Print and Attach Functions"""
        self._generate_e_waybill()

        # Mock GET response for get_e_waybill
        get_e_waybill_test_data = self.e_waybill_test_data.get("get_e_waybill")

        self._mock_e_waybill_response(
            data=get_e_waybill_test_data,
            match_list=[
                matchers.query_param_matcher(
                    get_e_waybill_test_data.get("request_data")
                ),
            ],
            method="GET",
            api="getewaybill",
        )

        fetch_e_waybill_data(
            doctype="Sales Invoice", docname=self.sales_invoice.name, attach=True
        )

        self.assertTrue(
            frappe.get_doc(
                "File",
                {
                    "attached_to_doctype": "Sales Invoice",
                    "attached_to_name": self.sales_invoice.name,
                },
            )
        )

    @responses.activate
    def test_cancel_e_waybill(self):
        """Test whitelisted method `cancel_e_waybill`"""

        self._generate_e_waybill()

        # test data to mock cancel e_waybill response
        test_data = self.e_waybill_test_data.get("cancel_e_waybill")

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

        cancel_e_waybill(
            doctype=self.sales_invoice.doctype,
            docname=self.sales_invoice.name,
            values=values,
        )

        # assertions
        self.assertTrue(
            frappe.get_doc(
                "e-Waybill Log",
                {"reference_name": self.sales_invoice.name, "is_cancelled": 1},
            )
        )

    @responses.activate
    def test_get_e_waybill_cancel_data(self):
        """Check if e-waybill cancel data is generated correctly"""
        values = frappe._dict(
            {
                "reason": "Data Entry Mistake",
                "remark": "For Test",
            }
        )

        self._generate_e_waybill()

        doc = load_doc("Sales Invoice", self.sales_invoice.name, "cancel")

        # Validate if e-waybill can be cancelled
        doc.get_onload().get("e_waybill_info", {})["created_on"] = add_to_date(
            get_datetime(),
            days=-3,
            as_datetime=True,
        )

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(e-Waybill can be cancelled only within 24.*)$"),
            EWaybillData(doc).validate_if_ewaybill_can_be_cancelled,
        )

        # assert if get_cancel_data dict equals to request data given in test records
        doc.get_onload().get("e_waybill_info", {}).update(
            {
                "created_on": get_datetime(),
            }
        )

        self.assertDictEqual(
            self.e_waybill_test_data.get("cancel_e_waybill").get("request_data"),
            EWaybillData(doc).get_e_waybill_cancel_data(values),
        )

    def test_get_all_item_details(self):
        """Tests:
        - validate length of GST/HSN Code in items
        - check if item details are generated correctly
        """
        si = create_sales_invoice(do_not_submit=True)

        hsn_codes = frappe.get_file_json(
            frappe.get_app_path(
                "india_compliance", "gst_india", "data", "hsn_codes.json"
            )
        )
        _bulk_insert_hsn_wise_items(hsn_codes)

        for i in range(0, 1000):
            hsn_code = random.choice(hsn_codes).get("hsn_code")
            if hsn_code == "61149090":
                continue

            si.append(
                "items",
                {
                    "item_code": hsn_code,
                    "item_name": "Test Item {}".format(i),
                    "qty": 1,
                    "rate": 100,
                    "gst_hsn_code": hsn_code,
                },
            )
        si.save()

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(e-Waybill can only be generated for upto.*)$"),
            EWaybillData(si).get_all_item_details,
        )

        # Assert get_all_item_details
        to_remove = [
            d
            for d in si.items
            if d.gst_hsn_code != "61149090" and d.item_code != "_Test Trading Goods 1"
        ]
        for item in to_remove:
            si.remove(item)
        si.save()

        self.assertListEqual(
            [
                {
                    "item_no": 1,
                    "qty": 1.0,
                    "taxable_value": 100.0,
                    "hsn_code": "61149090",
                    "item_name": "Test Trading Goods 1",
                    "uom": "NOS",
                    "cgst_amount": 0,
                    "cgst_rate": 0,
                    "sgst_amount": 0,
                    "sgst_rate": 0,
                    "igst_amount": 0,
                    "igst_rate": 0,
                    "cess_amount": 0,
                    "cess_rate": 0,
                    "cess_non_advol_amount": 0,
                    "cess_non_advol_rate": 0,
                    "tax_rate": 0.0,
                    "total_value": 100.0,
                }
            ],
            EWaybillData(si).get_all_item_details(),
        )

    @responses.activate
    def test_validate_transaction(self):
        """Test validation if ewaybill is already generated for the transaction"""
        test_data = self.e_waybill_test_data.get("goods_item_with_ewaybill")
        test_data.get("kwargs").update(
            {
                "transporter": "_Test Common Supplier",
                "distance": 10,
                "mode_of_transport": "Road",
            }
        )
        self.sales_invoice = create_sales_invoice(**test_data.get("kwargs"))

        self.sales_invoice.ewaybill = (
            test_data.get("response_data").get("result").get("ewayBillNo")
        )

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(e-Waybill already generated.*)$"),
            EWaybillData(self.sales_invoice).validate_transaction,
        )

    def test_validate_applicability(self):
        """
        Validates:
        - Required fields
        - Atleast one item with HSN for goods is required
        - Basic transporter details must be present
        - Transaction with Non GST Item is not allowed
        """

        test_data = self.e_waybill_test_data.get("goods_item_with_ewaybill")
        test_data.get("kwargs").update({"customer_address": "", "item_code": "999900"})
        self.sales_invoice = create_sales_invoice(**test_data.get("kwargs"))

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(.*is required to generate e-Waybill)$"),
            EWaybillData(self.sales_invoice).validate_applicability,
        )

        self.sales_invoice.customer_address = "_Test Registered Customer-Billing"
        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(e-Waybill cannot be generated because all items have.*)$"),
            EWaybillData(self.sales_invoice).validate_applicability,
        )

        append_item(
            self.sales_invoice,
            frappe._dict(
                {"item_code": "_Test Trading Goods 1", "gst_hsn_code": "61149090"}
            ),
        )
        self.sales_invoice.gst_transporter_id = ""
        self.sales_invoice.mode_of_transport = ""

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(Either GST Transporter ID or Mode.*)$"),
            EWaybillData(self.sales_invoice).validate_applicability,
        )

        self.sales_invoice.gst_transporter_id = "05AAACG2140A1ZL"
        self.sales_invoice.mode_of_transport = "Road"

        for item in self.sales_invoice.items:
            item.is_non_gst = 1

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(.*transactions with non-GST items)$"),
            EWaybillData(self.sales_invoice).validate_applicability,
        )

    @responses.activate
    def test_validate_if_e_waybill_is_set(self):
        """Test validdation if e-waybill not found"""
        self._generate_e_waybill()

        # validate if ewaybill is set
        self.sales_invoice.ewaybill = ""

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(No e-Waybill found for this document)$"),
            EWaybillData(self.sales_invoice).validate_if_e_waybill_is_set,
        )

    @responses.activate
    def test_check_e_waybill_validity(self):
        """Test validity before updating the e-waybill"""
        self._generate_e_waybill()

        doc = load_doc("Sales Invoice", self.sales_invoice.name, "submit")
        doc.get_onload().get("e_waybill_info", {})["valid_upto"] = add_to_date(
            get_datetime(),
            days=-2,
            as_datetime=True,
        )

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(e-Waybill cannot be modified after its.*)$"),
            EWaybillData(doc).check_e_waybill_validity,
        )

    @responses.activate
    def test_get_update_vehicle_data(self):
        """Test if vehicle data is generated correctly"""
        self._generate_e_waybill()

        doc = load_doc("Sales Invoice", self.sales_invoice.name, "submit")
        vehicle_info = frappe._dict(self.e_waybill_test_data.get("vehicle_info"))
        doc.vehicle_no = vehicle_info.get("vehicle_no")

        self.assertDictEqual(
            self.e_waybill_test_data.get("update_vehicle_info").get("request_data"),
            EWaybillData(doc).get_update_vehicle_data(vehicle_info),
        )

    @responses.activate
    def test_get_update_transporter_data(self):
        """Test if transporter data is generated correctly"""
        self._generate_e_waybill()

        doc = load_doc("Sales Invoice", self.sales_invoice.name, "submit")
        transporter_values = frappe._dict(
            self.e_waybill_test_data.get("transporter_values")
        )

        self.assertDictEqual(
            self.e_waybill_test_data.get("update_transporter").get("request_data"),
            EWaybillData(doc).get_update_transporter_data(transporter_values),
        )

    def test_validate_doctype_for_e_waybill(self):
        """Validate if doctype is supported for e-waybill"""
        purchase_invoice = create_purchase_invoice()

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(Only Sales Invoice and Delivery Note are supported.*)$"),
            EWaybillData,
            purchase_invoice,
        )

    # helper functions
    def _generate_e_waybill(self):
        """Generate e-waybill"""

        # Mock POST response for generate_e_waybill
        e_waybill_with_goods_item = self.e_waybill_test_data.goods_item_with_ewaybill
        self._mock_e_waybill_response(
            data=e_waybill_with_goods_item.get("response_data"),
            match_list=[
                matchers.query_string_matcher(e_waybill_with_goods_item.get("params")),
                matchers.json_params_matcher(
                    e_waybill_with_goods_item.get("request_data")
                ),
            ],
        )

        # Mock GET response for get_e_waybill
        get_e_waybill_test_data = self.e_waybill_test_data.get("get_e_waybill")

        self._mock_e_waybill_response(
            data=get_e_waybill_test_data.get("response_data"),
            match_list=[
                matchers.query_string_matcher(
                    get_e_waybill_test_data.get("request_data")
                ),
            ],
            method="GET",
            api="getewaybill",
        )

        generate_e_waybill(
            doctype="Sales Invoice",
            docname=self.sales_invoice.name,
        )

    def _mock_e_waybill_response(self, data, match_list, method="POST", api=None):
        """Mock e-waybill response for given data and match_list"""
        base_api = "/test/ewb/ewayapi/"
        api = base_api if not api else f"{base_api}{api}"
        url = BASE_URL + api

        response_method = responses.GET if method == "GET" else responses.POST

        responses.add(
            response_method,
            url,
            json=data,
            match=match_list,
            status=200,
        )


def update_dates_for_test_data(test_data):
    """Update dates in test data"""

    today_date = format_date(today(), DATE_FORMAT)
    current_datetime = now_datetime().strftime(DATETIME_FORMAT)
    next_day_datetime = add_to_date(getdate(), days=1).strftime(DATETIME_FORMAT)

    # Iterate over dict like { 'goods_item_with_ewaybill' : {...}}
    for key, value in test_data.items():
        if not value.get("response_data") and not value.get("request_data"):
            continue

        response_request = value.get("request_data")
        response_result = value.get("response_data").get("result")

        for k, v in response_result.items():
            if k == "ewayBillDate":
                response_result.update({k: current_datetime})
            if k == "validUpto":
                response_result.update({k: next_day_datetime})
            if k == "transUpdateDate":
                response_result.update({k: current_datetime})
            if k == "vehUpdateDate":
                response_result.update({k: current_datetime})
            if k == "cancelDate":
                response_result.update({k: current_datetime})
            if k == "docDate":
                response_result.update({k: today_date})

        if "docDate" in response_request:
            response_request.update({"docDate": today_date})

        if key == "get_e_waybill":
            for v in response_result.get("VehiclListDetails"):
                v.update({"enteredDate": current_datetime})


def _create_sales_invoice(test_data):
    """Generate Sales Invoice to test e-Waybill functionalities"""
    # update kwargs to process invoice
    kwargs = test_data.goods_item_with_ewaybill.get("kwargs")
    kwargs.update(
        {
            "transporter": "_Test Common Supplier",
            "distance": 10,
            "mode_of_transport": "Road",
        }
    )

    # set date and time in mocked response data according to the api response
    update_dates_for_test_data(test_data)

    si = create_sales_invoice(**kwargs, do_not_submit=True)
    si.gst_transporter_id = ""
    si.submit()
    return si


def _bulk_insert_hsn_wise_items(hsn_codes):
    frappe.db.bulk_insert(
        "Item",
        [
            "name",
            "item_code",
            "item_name",
            "creation",
            "modified",
            "owner",
            "modified_by",
            "gst_hsn_code",
            "description",
            "item_group",
            "stock_uom",
        ],
        [
            [
                code["hsn_code"],
                code["hsn_code"],
                "Test Item " + str(idx),
                get_datetime(),
                get_datetime(),
                frappe.session.user,
                frappe.session.user,
                code["hsn_code"],
                code["description"],
                "Services" if code["hsn_code"][:2] == "99" else "Products",
                "Nos",
            ]
            for idx, code in enumerate(hsn_codes, 13000)
        ],
        ignore_duplicates=True,
        chunk_size=251,
    )
