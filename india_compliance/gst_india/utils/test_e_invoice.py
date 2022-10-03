import json
import re

import jwt
import requests
import responses
from responses import matchers

import frappe
from frappe.tests.utils import FrappeTestCase, change_settings
from frappe.utils import get_datetime

from india_compliance.gst_india.api_classes.e_invoice import EInvoiceAPI
from india_compliance.gst_india.constants.e_invoice import CANCEL_REASON_CODES
from india_compliance.gst_india.utils import load_doc, parse_datetime
from india_compliance.gst_india.utils.e_invoice import (
    EInvoiceData,
    log_and_process_e_waybill_generation,
    log_e_invoice,
    validate_e_invoice_applicability,
    validate_if_e_invoice_can_be_cancelled,
)
from india_compliance.gst_india.utils.e_waybill import (
    EWaybillData,
    log_and_process_e_waybill,
)
from india_compliance.gst_india.utils.tests import create_sales_invoice


class TestEInvoice(FrappeTestCase):
    BASE_URL = "https://asp.resilient.tech"

    @classmethod
    def setUpClass(cls):
        frappe.db.set_value(
            "GST Settings",
            "GST Settings",
            {
                "enable_api": 1,
                "enable_e_invoice": 1,
                "auto_generate_e_invoice": 0,
                "enable_e_waybill": 1,
                "fetch_e_waybill_data": 0,
            },
        )
        cls.e_invoice_test_data = frappe.get_file_json(
            frappe.get_app_path("india_compliance", "tests", "e_invoice_test_data.json")
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

    @classmethod
    def tearDown(cls):
        frappe.db.rollback()

    @change_settings("Selling Settings", {"allow_multiple_items": 1})
    def test_get_data(self):
        """Validation test for more than 1000 items in sales invoice"""
        si = create_sales_invoice(do_not_submit=True)
        item_row = si.get("items")[0]

        for index in range(0, 1000):
            si.append(
                "items",
                {
                    "item_code": item_row.item_code,
                    "qty": item_row.qty,
                    "rate": item_row.rate,
                },
            )
        si.save()

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(e-Invoice can only be generated.*)$"),
            EInvoiceData(si).get_data,
        )

    @responses.activate
    def test_generate_e_invoice_with_goods_item(self):
        """Generate test e-Invoice for goods item"""
        test_data = self.e_invoice_test_data.get("goods_item_with_ewaybill")
        si = create_sales_invoice(**test_data.get("kwargs"))

        # Mock response for generating irn
        result = self._mock_e_invoice_response(si, test_data)

        self._generate_e_invoice(si, result)

        log_and_process_e_waybill_generation(si, result, with_irn=True)

        self.assertDocumentEqual(
            {"name": result.Irn},
            frappe.get_doc("e-Invoice Log", {"sales_invoice": si.name}),
        )
        self.assertDocumentEqual(
            {"name": result.EwbNo},
            frappe.get_doc("e-Waybill Log", {"reference_name": si.name}),
        )

    @responses.activate
    def test_generate_e_invoice_with_service_item(self):
        """Generate test e-Invoice for Service Item"""
        test_data = self.e_invoice_test_data.get("service_item")
        si = create_sales_invoice(**test_data.get("kwargs"))

        # Mock response for generating irn
        result = self._mock_e_invoice_response(si, test_data)

        self._generate_e_invoice(si, result)

        self.assertDocumentEqual(
            {"name": result.Irn},
            frappe.get_doc("e-Invoice Log", {"sales_invoice": si.name}),
        )

        self.assertFalse(result.EwbNo)

        self.assertFalse(
            frappe.db.get_value("e-Waybill Log", {"reference_name": si.name}, "name")
        )

    @responses.activate
    def test_return_e_invoice_with_goods_item(self):
        """Generate test e-Invoice for returned Sales Invoices"""
        test_data = self.e_invoice_test_data.get("return_invoice")

        si = create_sales_invoice(
            customer_address="_Test Registered Customer-Billing",
            shipping_address_name="_Test Registered Customer-Billing",
        )

        test_data.get("kwargs").update({"return_against": si.name})

        return_si = create_sales_invoice(**test_data.get("kwargs"))

        # Mock response for generating irn
        result = self._mock_e_invoice_response(
            frappe.get_doc("Sales Invoice", return_si.name), test_data
        )

        self._generate_e_invoice(return_si, result)

        self.assertDocumentEqual(
            {"name": result.Irn},
            frappe.get_doc("e-Invoice Log", {"sales_invoice": return_si.name}),
        )

        self.assertFalse(result.EwbNo)

        self.assertFalse(
            frappe.db.get_value(
                "e-Waybill Log", {"reference_name": return_si.name}, "name"
            )
        )

    @responses.activate
    def test_debit_note_e_invoice_with_goods_item(self):
        """Generate test e-Invoice for debit note with zero quantity"""
        test_data = self.e_invoice_test_data.get("debit_invoice")
        si = create_sales_invoice(
            customer_address="_Test Registered Customer-Billing",
            shipping_address_name="_Test Registered Customer-Billing",
        )

        test_data.get("kwargs").update({"return_against": si.name})
        debit_note = create_sales_invoice(**test_data.get("kwargs"), do_not_submit=True)

        debit_note.items[0].qty = 0
        debit_note.save()
        debit_note.submit()

        # Mock response for generating irn
        result = self._mock_e_invoice_response(debit_note, test_data)

        self._generate_e_invoice(debit_note, result)

        self.assertDocumentEqual(
            {"name": result.Irn},
            frappe.get_doc("e-Invoice Log", {"sales_invoice": debit_note.name}),
        )
        self.assertFalse(result.EwbNo)

        self.assertFalse(
            frappe.db.get_value(
                "e-Waybill Log", {"reference_name": debit_note.name}, "name"
            )
        )

    @responses.activate
    def test_cancel_e_invoice(self):
        """Test for generate and cancel e-Invoice
        - Test function `validate_if_e_invoice_can_be_cancelled`
        """

        test_data = self.e_invoice_test_data.get("goods_item_with_ewaybill")
        si = create_sales_invoice(**test_data.get("kwargs"))

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(IRN not found)$"),
            validate_if_e_invoice_can_be_cancelled,
            si,
        )

        # Mock response for generating irn
        result = self._mock_e_invoice_response(si, test_data)

        self._generate_e_invoice(si, result)
        log_and_process_e_waybill_generation(si, result, with_irn=True)

        si_doc = load_doc("Sales Invoice", si.name, "cancel")

        si_doc.get_onload().get("e_invoice_info", {}).update({"acknowledged_on": None})

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(e-Invoice can only be cancelled.*)$"),
            validate_if_e_invoice_can_be_cancelled,
            si_doc,
        )

        values = frappe._dict(
            {"reason": "Data Entry Mistake", "remark": "Data Entry Mistake"}
        )

        self._cancel_e_waybill(si_doc, values)
        self._cancel_e_invoice(si_doc, values)

        self.assertDocumentEqual({"einvoice_status": "Cancelled", "irn": ""}, si_doc)
        self.assertDocumentEqual({"ewaybill": ""}, si_doc)

    def test_validate_e_invoice_applicability(self):
        """Test if e_invoicing is applicable"""

        si = create_sales_invoice(
            customer="_Test Unregistered Customer",
            gst_category="Unregistered",
            do_not_submit=True,
        )
        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(e-Invoice is not applicable for invoices.*)$"),
            validate_e_invoice_applicability,
            si,
        )

        si.update(
            {
                "gst_category": "Registered Regular",
                "customer": "_Test Registered Customer",
            }
        )
        si.save(ignore_permissions=True)
        frappe.db.set_single_value(
            "GST Settings", "e_invoice_applicable_from", "2045-05-18"
        )

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(e-Invoice is not applicable for invoices before.*)$"),
            validate_e_invoice_applicability,
            si,
        )

        frappe.db.set_single_value(
            "GST Settings", "e_invoice_applicable_from", get_datetime()
        )

    def _generate_e_invoice(self, doc, result):
        doc.db_set(
            {
                "irn": result.Irn,
                "einvoice_status": "Generated",
            }
        )

        decoded_invoice = frappe.parse_json(
            jwt.decode(result.SignedInvoice, options={"verify_signature": False})[
                "data"
            ]
        )

        log_e_invoice(
            doc,
            {
                "irn": doc.irn,
                "sales_invoice": doc.name,
                "acknowledgement_number": result.AckNo,
                "acknowledged_on": parse_datetime(result.AckDt),
                "signed_invoice": result.SignedInvoice,
                "signed_qr_code": result.SignedQRCode,
                "invoice_data": frappe.as_json(decoded_invoice, indent=4),
            },
        )

    def _cancel_e_invoice(self, doc, values):
        cancel_irn_test_data = self.e_invoice_test_data.get("cancel_e_invoice")
        cancel_irn_test_data.get("response_data").get("result").update({"Irn": doc.irn})

        request_data = {
            "Irn": doc.irn,
            "Cnlrsn": CANCEL_REASON_CODES[values.reason],
            "Cnlrem": values.remark if values.remark else values.reason,
        }

        result = self._mock_e_invoice_response(
            doc, cancel_irn_test_data, "ei/api/invoice/cancel", request_data
        )

        doc.db_set({"einvoice_status": "Cancelled", "irn": ""})

        log_e_invoice(
            doc,
            {
                "name": result.Irn,
                "is_cancelled": 1,
                "cancel_reason_code": values.reason,
                "cancel_remark": values.remark,
                "cancelled_on": parse_datetime(result.CancelDate),
            },
        )

    def _cancel_e_waybill(self, doc, values):
        test_data = self.e_invoice_test_data.get("cancel_e_waybill")
        test_data.get("response_data").get("result").update(
            {"ewayBillNo": doc.ewaybill}
        )

        request_data = EWaybillData(doc).get_e_waybill_cancel_data(values)

        result = self._mock_e_invoice_response(
            doc, test_data, "/ei/api/ewayapi", request_data
        )

        log_and_process_e_waybill(
            doc,
            {
                "name": doc.ewaybill,
                "is_cancelled": 1,
                "cancel_reason_code": CANCEL_REASON_CODES[values.reason],
                "cancel_remark": values.remark if values.remark else values.reason,
                "cancelled_on": parse_datetime(result.cancelDate, day_first=True),
            },
        )

        doc.db_set("ewaybill", "")

    def _mock_e_invoice_response(
        self, doc, data, api="ei/api/invoice", request_data=None
    ):
        if not request_data:
            request_data = EInvoiceData(doc).get_data()

        url = self.BASE_URL + "/test/" + api

        responses.add(
            responses.POST,
            url,
            body=json.dumps(data.get("response_data")),
            match=[matchers.json_params_matcher(request_data)],
            status=200,
        )

        api = EInvoiceAPI(doc)
        api.default_headers.update({"requestid": frappe.generate_hash(length=12)})

        response = requests.post(
            url,
            headers=api.default_headers,
            json=request_data,
        )

        response_json = response.json(object_hook=frappe._dict)
        return response_json.get("result", response_json)
