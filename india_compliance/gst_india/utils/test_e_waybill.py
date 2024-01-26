import datetime
import random
import re

import pytz
import responses
import time_machine
from responses import matchers

import frappe
from frappe.tests.utils import FrappeTestCase, change_settings
from frappe.utils import add_to_date, get_datetime, now_datetime, today
from frappe.utils.data import format_date
from erpnext.controllers.sales_and_purchase_return import make_return_doc

from india_compliance.gst_india.api_classes.base import BASE_URL
from india_compliance.gst_india.utils import load_doc
from india_compliance.gst_india.utils.e_invoice import (
    retry_e_invoice_e_waybill_generation,
)
from india_compliance.gst_india.utils.e_waybill import (
    EWaybillData,
    cancel_e_waybill,
    fetch_e_waybill_data,
    generate_e_waybill,
    get_e_waybills_to_extend,
    schedule_ewaybill_for_extension,
    update_transporter,
    update_vehicle_info,
)
from india_compliance.gst_india.utils.tests import (
    _append_taxes,
    append_item,
    create_purchase_invoice,
    create_sales_invoice,
    create_transaction,
)

DATETIME_FORMAT = "%d/%m/%Y %I:%M:%S %p"
DATE_FORMAT = "dd/mm/yyyy"


class TestEWaybill(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

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
                "enable_retry_einv_ewb_generation": 1,
                "is_retry_einv_ewb_generation_pending": 0,
            },
        )

        cls.e_waybill_test_data = frappe._dict(
            frappe.get_file_json(
                frappe.get_app_path(
                    "india_compliance", "gst_india", "data", "test_e_waybill.json"
                )
            )
        )

    @classmethod
    def setUp(cls):
        update_dates_for_test_data(cls.e_waybill_test_data)

    def test_get_data(self):
        si = self.create_sales_invoice_for("goods_item_with_ewaybill")
        e_waybill_data = EWaybillData(si).get_data()
        test_data = self.e_waybill_test_data.goods_item_with_ewaybill.get(
            "request_data"
        )

        self.assertDictContainsSubset(
            e_waybill_data,
            test_data,
        )

    @change_settings("GST Settings", {"fetch_e_waybill_data": 1})
    @responses.activate
    def test_generate_e_waybill(self):
        """Test whitelisted method `generate_e_waybill`"""
        si = self.create_sales_invoice_for("goods_item_with_ewaybill")
        self._generate_e_waybill(si.name)

        self.assertDocumentEqual(
            {
                "name": self.e_waybill_test_data.goods_item_with_ewaybill.get(
                    "response_data"
                )
                .get("result")
                .get("ewayBillNo")
            },
            frappe.get_doc("e-Waybill Log", {"reference_name": si.name}),
        )

    @responses.activate
    def test_update_vehicle_info(self):
        """Test whitelisted function `update_vehicle_info`"""
        si = self.create_sales_invoice_for("goods_item_with_ewaybill")
        self._generate_e_waybill(si.name)

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
            docname=si.name,
            values=frappe._dict(vehicle_data.get("values")),
        )

        # assertions
        expected_comment = "Vehicle Info has been updated by <strong>Administrator</strong>.<br><br> New details are: <br><strong>Vehicle No</strong>: GJ07DL9001 <br><strong>Mode of Transport</strong>: Road <br><strong>GST Vehicle Type</strong>: Regular <br><strong>Place of Change</strong>: Test City <br><strong>State</strong>: Gujarat <br>"

        self.assertDocumentEqual(
            {"name": vehicle_data.get("request_data").get("ewbNo")},
            frappe.get_doc("e-Waybill Log", {"reference_name": si.name}),
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
        si = self.create_sales_invoice_for("goods_item_with_ewaybill")
        self._generate_e_waybill(si.name)

        # get test data from test json and update date accordingly
        transporter_data = self.e_waybill_test_data.get("update_transporter")

        # Mock response for UPDATETRANSPORTER
        self._mock_e_waybill_response(
            data=transporter_data.get("response_data"),
            match_list=[
                matchers.query_string_matcher(transporter_data.get("params")),
                matchers.json_params_matcher(transporter_data.get("request_data")),
            ],
        )

        update_transporter(
            doctype="Sales Invoice",
            docname=si.name,
            values=transporter_data.get("values"),
        )

        # assertions
        self.assertDocumentEqual(
            {"name": transporter_data.get("request_data").get("ewbNo")},
            frappe.get_doc("e-Waybill Log", {"reference_name": si.name}),
        )

        self.assertDocumentEqual(
            {
                "reference_doctype": "e-Waybill Log",
                "reference_name": transporter_data.get("request_data").get("ewbNo"),
                "content": "Transporter Info has been updated by <strong>Administrator</strong>. New Transporter ID is <strong>05AAACG2140A1ZL</strong>.",
            },
            frappe.get_doc(
                "Comment",
                {"reference_name": transporter_data.get("request_data").get("ewbNo")},
            ),
        )

    @change_settings("GST Settings", {"fetch_e_waybill_data": 1})
    @responses.activate
    def test_fetch_e_waybill_data(self):
        """Test e-Waybill Print and Attach Functions"""
        si = self.create_sales_invoice_for("goods_item_with_ewaybill")
        self._generate_e_waybill(si.name)

        fetch_e_waybill_data(doctype="Sales Invoice", docname=si.name, attach=False)

    @responses.activate
    def test_credit_note_e_waybill(self):
        si = create_sales_invoice(
            vehicle_no="GJ05DL9009",
            item_tax_template="GST 12% - _TIRC",
            rate=7.6,
            is_in_state=True,
            do_not_submit=True,
        )

        append_item(
            si,
            frappe._dict(rate=7.6, item_tax_template="GST 12% - _TIRC", uom="Nos"),
        )
        si.save()
        si.submit()

        self._generate_e_waybill(
            si.name, test_data=self.e_waybill_test_data.goods_with_taxes
        )

        credit_note = make_return_doc("Sales Invoice", si.name)
        credit_note.vehicle_no = "GJ05DL9009"
        credit_note.save()
        credit_note.submit()

        # Assert if request data given in Json
        self.assertDictEqual(
            self.e_waybill_test_data.credit_note.get("request_data"),
            EWaybillData(credit_note).get_data(),
        )

    @responses.activate
    def test_cancel_e_waybill(self):
        """Test whitelisted method `cancel_e_waybill`"""
        si = self.create_sales_invoice_for("goods_item_with_ewaybill")
        self._generate_e_waybill(si.name)

        # test data to mock cancel e_waybill response
        e_waybill_cancel_data = self.e_waybill_test_data.get("cancel_e_waybill")

        # Mock response for CANEWB
        self._mock_e_waybill_response(
            data=e_waybill_cancel_data.get("response_data"),
            match_list=[
                matchers.query_string_matcher(e_waybill_cancel_data.get("params")),
                matchers.json_params_matcher(e_waybill_cancel_data.get("request_data")),
            ],
        )

        cancel_e_waybill(
            doctype=si.doctype,
            docname=si.name,
            values=e_waybill_cancel_data.get("values"),
        )

        # assertions
        self.assertTrue(
            frappe.get_doc(
                "e-Waybill Log",
                {"reference_name": si.name, "is_cancelled": 1},
            )
        )

    @responses.activate
    def test_get_e_waybill_cancel_data(self):
        """Check if e-waybill cancel data is generated correctly"""
        si = self.create_sales_invoice_for("goods_item_with_ewaybill")
        self._generate_e_waybill(si.name)

        doc = load_doc("Sales Invoice", si.name, "cancel")

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

        e_waybill_cancel_data = self.e_waybill_test_data.get("cancel_e_waybill")

        self.assertDictEqual(
            e_waybill_cancel_data.get("request_data"),
            EWaybillData(doc).get_data_for_cancellation(
                frappe._dict(e_waybill_cancel_data.get("values"))
            ),
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

            append_item(
                si,
                frappe._dict(
                    item_code=hsn_code,
                    item_name="Test Item {}".format(i),
                    rate=100,
                    gst_hsn_code=hsn_code,
                ),
            )

        si.save()

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(e-Waybill can only be .* HSN/SAC Codes)$"),
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
                    "gst_treatment": "Nil-Rated",
                }
            ],
            EWaybillData(si).get_all_item_details(),
        )

        for i in range(0, 250):
            append_item(si)

        _append_taxes(si, ("CGST", "SGST"))
        si.save()

        self.assertListEqual(
            list(EWaybillData(si).get_all_item_details()),
            [
                {
                    "hsn_code": "61149090",
                    "uom": "NOS",
                    "item_name": "",
                    "cgst_rate": 9.0,
                    "sgst_rate": 9.0,
                    "igst_rate": 0,
                    "cess_rate": 0,
                    "cess_non_advol_rate": 0,
                    "item_no": 1,
                    "qty": 251.0,
                    "taxable_value": 25100.0,
                }
            ],
        )

    @responses.activate
    def test_validate_transaction(self):
        """Test validation if ewaybill is already generated for the transaction"""
        e_waybill_data = self.e_waybill_test_data.goods_item_with_ewaybill

        si = self.create_sales_invoice_for("goods_item_with_ewaybill")
        self._generate_e_waybill(si.name)
        si.ewaybill = (
            e_waybill_data.get("response_data").get("result").get("ewayBillNo")
        )

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(e-Waybill already generated.*)$"),
            EWaybillData(si).validate_transaction,
        )

    def test_validate_applicability(self):
        """
        Validates:
        - Required fields
        - Atleast one item with HSN for goods is required
        - Basic transporter details must be present
        - Transaction with Non GST Item is not allowed
        """

        args = self.e_waybill_test_data.get("goods_item_with_ewaybill").get("kwargs")
        args.update({"customer_address": "", "item_code": "_Test Service Item"})
        si = create_sales_invoice(**args, do_not_submit=True)

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(.*is required to generate e-Waybill)$"),
            EWaybillData(si).validate_applicability,
        )

        si.customer_address = "_Test Registered Customer-Billing"
        si.company_address = "Test Address - 1"

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(e-Waybill cannot be generated because all items have.*)$"),
            EWaybillData(si).validate_applicability,
        )

        append_item(
            si,
            frappe._dict(
                {"item_code": "_Test Trading Goods 1", "gst_hsn_code": "61149090"}
            ),
        )
        si.update({"gst_transporter_id": "", "mode_of_transport": ""})

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(Either GST Transporter ID or Mode.*)$"),
            EWaybillData(si).validate_applicability,
        )

        si.update(
            {"gst_transporter_id": "05AAACG2140A1ZL", "mode_of_transport": "Road"}
        )

        si.items[0].gst_treatment = "Non-GST"

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(.*transactions with non-GST items)$"),
            EWaybillData(si).validate_applicability,
        )

        si.items[0].gst_treatment = "Taxable"
        si.update(
            {
                "company_gstin": "05AAACG2115R1ZN",
                "billing_address_gstin": "05AAACG2115R1ZN",
            }
        )
        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(.*billing GSTIN is same as company GSTIN.*)$"),
            EWaybillData(si).validate_applicability,
        )

    @responses.activate
    def test_validate_if_e_waybill_is_set(self):
        """Test validdation if e-waybill not found"""
        si = self.create_sales_invoice_for("goods_item_with_ewaybill")
        self._generate_e_waybill(si.name)

        # validate if ewaybill is set
        si.ewaybill = ""

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(No e-Waybill found for this document)$"),
            EWaybillData(si).validate_if_e_waybill_is_set,
        )

    @responses.activate
    def test_check_e_waybill_validity(self):
        """Test validity before updating the e-waybill"""
        si = self.create_sales_invoice_for("goods_item_with_ewaybill")
        self._generate_e_waybill(si.name)

        doc = load_doc("Sales Invoice", si.name, "submit")
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
        si = self.create_sales_invoice_for("goods_item_with_ewaybill")
        self._generate_e_waybill(si.name)

        doc = load_doc("Sales Invoice", si.name, "submit")
        vehicle_info = self.e_waybill_test_data.get("update_vehicle_info")

        doc.vehicle_no = vehicle_info.get("values").get("vehicle_no")

        self.assertDictEqual(
            vehicle_info.get("request_data"),
            EWaybillData(doc).get_update_vehicle_data(
                frappe._dict(vehicle_info.get("values"))
            ),
        )

    @responses.activate
    def test_get_update_transporter_data(self):
        """Test if transporter data is generated correctly"""
        si = self.create_sales_invoice_for("goods_item_with_ewaybill")
        self._generate_e_waybill(si.name)

        doc = load_doc("Sales Invoice", si.name, "submit")
        transporter_data = self.e_waybill_test_data.get("update_transporter")

        self.assertDictEqual(
            transporter_data.get("request_data"),
            EWaybillData(doc).get_update_transporter_data(
                frappe._dict(transporter_data.get("values"))
            ),
        )

    @responses.activate
    def test_get_extend_validity_data(self):
        """Test if extend e-waybill validity data is generated correctly"""
        si = self.create_sales_invoice_for("goods_item_with_ewaybill")
        self._generate_e_waybill(si.name)
        doc = load_doc("Sales Invoice", si.name, "submit")

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(e-Waybill can be extended between.*)$"),
            EWaybillData(doc).validate_if_e_waybill_can_be_extend,
        )

        add_to_date(
            get_datetime(),
            hours=8,
            as_datetime=True,
        )

        extend_validity_data = self.e_waybill_test_data.get("extend_validity")
        values = frappe._dict(extend_validity_data.get("values"))

        values.remaining_distance = None

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(Distance is mandatory to extend .*)$"),
            EWaybillData(doc).validate_remaining_distance,
            values,
        )

        values.remaining_distance = 15

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(
                r"^(Remaining distance should be less than or equal to actual .*)$"
            ),
            EWaybillData(doc).validate_remaining_distance,
            values,
        )

        values.remaining_distance = 5
        values.consignment_status = "In Transit"

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(Transit Type is should be one of.*)$"),
            EWaybillData(doc).validate_transit_type,
            values,
        )

        values.consignment_status = "In Movement"

        with time_machine.travel(get_datetime(), tick=False) as traveller:
            traveller.shift(datetime.timedelta(hours=18))

            self.assertDictEqual(
                extend_validity_data.get("request_data"),
                EWaybillData(doc).get_extend_validity_data(values),
            )

    @responses.activate
    def test_schedule_e_waybill_for_extension(self):
        si = self.create_sales_invoice_for("goods_item_with_ewaybill")
        self._generate_e_waybill(si.name, force=True)
        doc = load_doc("Sales Invoice", si.name, "submit")

        valid_upto = frappe.db.get_value("e-Waybill Log", doc.ewaybill, "valid_upto")
        scheduled_time = add_to_date(valid_upto, hours=1)

        extend_validity_data = self.e_waybill_test_data.get("extend_validity")
        values = frappe._dict(extend_validity_data.get("values"))

        schedule_ewaybill_for_extension(
            doctype="Sales Invoice",
            docname=si.name,
            values=values,
            scheduled_time=scheduled_time,
        )

        extension_scheduled = frappe.db.get_value(
            "e-Waybill Log", doc.ewaybill, "extension_scheduled"
        )
        self.assertEqual(
            extension_scheduled,
            1,
            "e-waybill should be scheduled for extension",
        )

        with time_machine.travel(
            scheduled_time.replace().astimezone(pytz.utc), tick=False
        ):
            e_waybills_to_extend = get_e_waybills_to_extend()

            self.assertTrue(
                any(
                    doc.ewaybill == ewaybill.get("e_waybill_number")
                    for ewaybill in e_waybills_to_extend
                ),
                "e-Waybill not found in list of scheduled e-Waybills",
            )

    def test_validate_doctype_for_e_waybill(self):
        """Validate if doctype is supported for e-waybill"""
        purchase_order = create_transaction(doctype="Purchase Order")

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(
                r"^(Only Sales Invoice, Purchase Invoice, Delivery Note, Purchase Receipt are supported.*)$"
            ),
            EWaybillData,
            purchase_order,
        )

    @responses.activate
    def test_invoice_update_after_submit(self):
        si = self.create_sales_invoice_for("goods_item_with_ewaybill")
        self._generate_e_waybill(si.name)
        doc = load_doc("Sales Invoice", si.name, "submit")

        doc.group_same_items = True
        doc.save()

        self.assertEqual(
            frappe.parse_json(frappe.message_log[-1]).get("message"),
            "You have already generated e-Waybill/e-Invoice for this document."
            " This could result in mismatch of item details in e-Waybill/e-Invoice with print format.",
        )

    @change_settings("GST Settings", {"enable_e_waybill_from_dn": 1})
    @responses.activate
    def test_e_waybill_for_dn_with_different_gstin(self):
        """Test to generate e-waybill for Delivery Note with different GSTIN"""
        dn_with_different_gstin_data = self.e_waybill_test_data.get(
            "dn_with_different_gstin"
        )
        different_gstin_dn = self._create_delivery_note("dn_with_different_gstin")

        self._generate_e_waybill(
            different_gstin_dn.name, "Delivery Note", dn_with_different_gstin_data
        )

        self.assertDocumentEqual(
            {
                "name": dn_with_different_gstin_data.get("response_data")
                .get("result")
                .get("ewayBillNo")
            },
            frappe.get_doc(
                "e-Waybill Log", {"reference_name": different_gstin_dn.name}
            ),
        )

        #  Return Note
        is_return_dn_with_different_gstin_data = self.e_waybill_test_data.get(
            "is_return_dn_with_different_gstin"
        )

        return_note = make_return_doc("Delivery Note", different_gstin_dn.name).submit()

        self._generate_e_waybill(
            return_note.name, "Delivery Note", is_return_dn_with_different_gstin_data
        )

        self.assertDocumentEqual(
            {
                "name": is_return_dn_with_different_gstin_data.get("response_data")
                .get("result")
                .get("ewayBillNo")
            },
            frappe.get_doc("e-Waybill Log", {"reference_name": return_note.name}),
        )

    @change_settings("GST Settings", {"enable_e_waybill_from_dn": 1})
    @responses.activate
    def test_e_waybill_for_dn_with_same_gstin(self):
        """Test to generate e-waybill for Delivery Note with Same GSTIN"""
        dn_with_same_gstin_data = self.e_waybill_test_data.get("dn_with_same_gstin")
        same_gstin_dn = self._create_delivery_note("dn_with_same_gstin")

        self._generate_e_waybill(
            same_gstin_dn.name, "Delivery Note", dn_with_same_gstin_data
        )

        self.assertDocumentEqual(
            {
                "name": dn_with_same_gstin_data.get("response_data")
                .get("result")
                .get("ewayBillNo")
            },
            frappe.get_doc("e-Waybill Log", {"reference_name": same_gstin_dn.name}),
        )

        # Return Note
        return_note = make_return_doc("Delivery Note", same_gstin_dn.name)
        return_note.submit()

        is_return_dn_with_same_gstin_data = self.e_waybill_test_data.get(
            "is_return_dn_with_same_gstin"
        )

        self._generate_e_waybill(
            return_note.name, "Delivery Note", is_return_dn_with_same_gstin_data
        )

        self.assertDocumentEqual(
            {
                "name": is_return_dn_with_same_gstin_data.get("response_data")
                .get("result")
                .get("ewayBillNo")
            },
            frappe.get_doc("e-Waybill Log", {"reference_name": return_note.name}),
        )

    @change_settings("GST Settings", {"enable_e_waybill_from_pi": 1})
    @responses.activate
    def test_e_waybill_for_pi_with_unregistered_supplier(self):
        purchase_invoice_data = self.e_waybill_test_data.get(
            "pi_data_for_unregistered_supplier"
        )
        purchase_invoice = create_purchase_invoice(
            **purchase_invoice_data.get("kwargs")
        )

        self._generate_e_waybill(
            purchase_invoice.name, "Purchase Invoice", purchase_invoice_data
        )

        self.assertDocumentEqual(
            {
                "name": purchase_invoice_data.get("response_data")
                .get("result")
                .get("ewayBillNo")
            },
            frappe.get_doc("e-Waybill Log", {"reference_name": purchase_invoice.name}),
        )

    @change_settings("GST Settings", {"enable_e_waybill_from_pi": 1})
    @responses.activate
    def test_e_waybill_for_registered_purchase(self):
        purchase_invoice_data = self.e_waybill_test_data.get(
            "pi_data_for_registered_supplier"
        )

        purchase_invoice = create_purchase_invoice(
            **purchase_invoice_data.get("kwargs"), do_not_submit=True
        )

        purchase_invoice.bill_no = ""

        # Bill No Validation
        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(Bill No is mandatory.*)$"),
            EWaybillData(purchase_invoice).validate_bill_no_for_purchase,
        )

        purchase_invoice.bill_no = "1234"
        purchase_invoice.submit()

        #  Test get_data
        self.assertDictContainsSubset(
            EWaybillData(purchase_invoice).get_data(),
            purchase_invoice_data.get("request_data"),
        )

        self._generate_e_waybill(
            purchase_invoice.name, "Purchase Invoice", purchase_invoice_data
        )

        # Return Note
        return_note = make_return_doc("Purchase Invoice", purchase_invoice.name)
        return_note.distance = 10
        return_note.vehicle_no = "GJ05DL9009"
        return_note.submit()

        return_pi_data = self.e_waybill_test_data.get(
            "purchase_return_for_registered_supplier"
        )

        self._generate_e_waybill(return_note.name, "Purchase Invoice", return_pi_data)

        self.assertDocumentEqual(
            {
                "name": return_pi_data.get("response_data")
                .get("result")
                .get("ewayBillNo")
            },
            frappe.get_doc("e-Waybill Log", {"reference_name": return_note.name}),
        )

    @responses.activate
    def test_gst_error_retry_enabled(self):
        """Test to check if e-waybill status is set to Auto Retry on GST Server Error when Retry e-Invoice / e-Waybill Generation is enabled"""
        si = self.create_sales_invoice_for("goods_item_with_ewaybill")
        self._generate_e_waybill(
            si.name, test_data=self.e_waybill_test_data.gsp_gst_down_error
        )

        si = load_doc("Sales Invoice", si.name, "submit")

        self.assertEqual(si.e_waybill_status, "Auto-Retry")
        self.assertEqual(
            frappe.get_cached_value(
                "GST Settings", "GST Settings", "is_retry_einv_ewb_generation_pending"
            ),
            1,
        )

        retry_ewb_test_date = self.e_waybill_test_data.goods_item_with_ewaybill

        self._mock_e_waybill_response(
            data=retry_ewb_test_date.get("response_data"),
            match_list=[
                matchers.query_string_matcher(retry_ewb_test_date.get("params")),
                matchers.json_params_matcher(retry_ewb_test_date.get("request_data")),
            ],
            replace=True,
        )

        retry_e_invoice_e_waybill_generation()
        si = load_doc("Sales Invoice", si.name, "submit")

        self.assertEqual(si.e_waybill_status, "Generated")
        self.assertEqual(
            si.ewaybill,
            str(
                retry_ewb_test_date.get("response_data").get("result").get("ewayBillNo")
            ),
        )

    @change_settings("GST Settings", {"enable_retry_einv_ewb_generation": 0})
    @responses.activate
    def test_gst_error_retry_disabled(self):
        """Test to check if e-waybill status is set to Auto Retry on GST Server Error when Retry e-Invoice / e-Waybill Generation is disabled"""
        si = self.create_sales_invoice_for("goods_item_with_ewaybill")
        self._generate_e_waybill(
            si.name, test_data=self.e_waybill_test_data.gsp_gst_down_error
        )

        si = load_doc("Sales Invoice", si.name, "submit")

        self.assertEqual(si.e_waybill_status, "Failed")
        self.assertEqual(
            frappe.get_cached_value(
                "GST Settings", "GST Settings", "is_retry_einv_ewb_generation_pending"
            ),
            0,
        )

    # helper functions
    def _generate_e_waybill(
        self, docname=None, doctype="Sales Invoice", test_data=None, force=False
    ):
        """
        Mocks response for generate_e_waybill and get_e_waybill.
        Calls generate_e_waybill function.

        Args:
            doctype (str, optional): Defaults to "Sales Invoice".
            docname (str, optional): Defaults to None.
            test_data (dict, optional): Defaults to None.
        """

        if not test_data:
            test_data = self.e_waybill_test_data.goods_item_with_ewaybill

        # Mock POST response for generate_e_waybill
        self._mock_e_waybill_response(
            data=test_data.get("response_data"),
            match_list=[
                matchers.query_string_matcher(test_data.get("params")),
                matchers.json_params_matcher(test_data.get("request_data")),
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

        values = (
            frappe._dict(test_data.get("values")) if test_data.get("values") else None
        )

        generate_e_waybill(doctype=doctype, docname=docname, values=values, force=force)

    def _mock_e_waybill_response(
        self, data, match_list, method="POST", api=None, replace=False
    ):
        """
        Mock e-waybill response for given data and match_list

        Args:
            data (dict): Expected Response data
            match_list (list): List of matchers. Response will be mocked only if all matchers are satisfied.
                eg, [
                    matchers.query_string_matcher(params),
                    matchers.json_params_matcher(request_data),
                ]

            method (str, optional): HTTP method. Defaults to "POST".
            api (str, optional): API name. Defaults to None.
            replace (bool, optional): Replace existing mock response. Defaults to False.

        """
        base_api = "/test/ewb/ewayapi/"
        api = base_api if not api else f"{base_api}{api}"
        url = BASE_URL + api

        response_method = responses.GET if method == "GET" else responses.POST
        # responses.add or responses.replace
        getattr(responses, "replace" if replace else "add")(
            response_method,
            url,
            json=data,
            match=match_list,
            status=200,
        )

    def create_sales_invoice_for(self, test_case):
        """Generate Sales Invoice to test e-Waybill functionalities"""
        # update kwargs to process invoice
        invoice_args = self.e_waybill_test_data.get(test_case).get("kwargs")
        invoice_args.update(
            {
                "transporter": "_Test Common Supplier",
                "distance": 10,
                "mode_of_transport": "Road",
            }
        )

        # set date and time in mocked response data according to the api response
        update_dates_for_test_data(self.e_waybill_test_data)

        si = create_sales_invoice(**invoice_args, do_not_submit=True)
        si.gst_transporter_id = ""
        si.submit()

        return si

    def _create_delivery_note(self, test_case):
        """Generate Delivery Note to test e-Waybill functionalities"""
        doc_args = self.e_waybill_test_data.get(test_case).get("kwargs")
        doc_args.update({"doctype": "Delivery Note"})

        delivery_note = create_transaction(**doc_args)
        return delivery_note


def update_dates_for_test_data(test_data):
    """Update dates in test data"""

    today_date = format_date(today(), DATE_FORMAT)
    current_datetime = now_datetime().strftime(DATETIME_FORMAT)
    next_day_datetime = add_to_date(get_datetime(), days=1).strftime(DATETIME_FORMAT)

    # Iterate over dict like { 'goods_item_with_ewaybill' : {...}}
    for key, value in test_data.items():
        if not value.get("response_data") and not value.get("request_data"):
            continue

        response_request = value.get("request_data")
        response_result = value.get("response_data").get("result", {})

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
            if k == "updatedDate":
                response_result.update({k: current_datetime})

        if "docDate" in response_request:
            response_request.update({"docDate": today_date})

        if key == "get_e_waybill":
            for v in response_result.get("VehiclListDetails"):
                v.update({"enteredDate": current_datetime})


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
