import json
import re

import responses
from responses import matchers

import frappe
from frappe.tests.utils import FrappeTestCase, change_settings
from frappe.utils import get_datetime, now_datetime
from frappe.utils.data import format_date

from india_compliance.gst_india.utils.e_invoice import (
    EInvoiceData,
    cancel_e_invoice,
    generate_e_invoice,
    validate_e_invoice_applicability,
    validate_if_e_invoice_can_be_cancelled,
)
from india_compliance.gst_india.utils.tests import create_sales_invoice


class TestEInvoice(FrappeTestCase):
    BASE_URL = "https://asp.resilient.tech"

    @classmethod
    def setUpClass(cls):
        print(frappe._dict(frappe.get_site_config()))
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
        data = self.e_invoice_test_data.get("goods_item_with_ewaybill")
        self.update_doc_details(data)

        si = create_sales_invoice(**data.get("kwargs"))

        self._generate_e_invoice(data, si.name)

        self.assertDocumentEqual(
            {"name": data.get("response_data").get("result").get("Irn")},
            frappe.get_doc("e-Invoice Log", {"sales_invoice": si.name}),
        )
        self.assertDocumentEqual(
            {"name": data.get("response_data").get("result").get("EwbNo")},
            frappe.get_doc("e-Waybill Log", {"reference_name": si.name}),
        )

    @responses.activate
    def test_generate_e_invoice_with_service_item(self):
        """Generate test e-Invoice for Service Item"""
        data = self.e_invoice_test_data.get("service_item")
        self.update_doc_details(data)

        si = create_sales_invoice(**data.get("kwargs"))

        self._generate_e_invoice(data, si.name)

        self.assertDocumentEqual(
            {"name": data.get("response_data").get("result").get("Irn")},
            frappe.get_doc("e-Invoice Log", {"sales_invoice": si.name}),
        )

        self.assertFalse(
            frappe.db.get_value("e-Waybill Log", {"reference_name": si.name}, "name")
        )

    @responses.activate
    def test_return_e_invoice_with_goods_item(self):
        """Generate test e-Invoice for returned Sales Invoices"""

        data = self.e_invoice_test_data.get("return_invoice")

        si = create_sales_invoice(
            customer_address="_Test Registered Customer-Billing",
            shipping_address_name="_Test Registered Customer-Billing",
        )

        self.update_doc_details(data, inv_no=si.name, is_return=True)

        data.get("kwargs").update({"return_against": si.name})

        return_si = create_sales_invoice(**data.get("kwargs"))

        self._generate_e_invoice(data, return_si.name)

        self.assertDocumentEqual(
            {"name": data.get("response_data").get("result").get("Irn")},
            frappe.get_doc("e-Invoice Log", {"sales_invoice": return_si.name}),
        )

        self.assertFalse(
            frappe.db.get_value(
                "e-Waybill Log", {"reference_name": return_si.name}, "name"
            )
        )

    @responses.activate
    def test_debit_note_e_invoice_with_goods_item(self):
        """Generate test e-Invoice for debit note with zero quantity"""

        data = self.e_invoice_test_data.get("debit_invoice")
        self.update_doc_details(data)

        si = create_sales_invoice(**data.get("kwargs"))

        self._generate_e_invoice(data, si.name)

        self.assertDocumentEqual(
            {"name": data.get("response_data").get("result").get("Irn")},
            frappe.get_doc("e-Invoice Log", {"sales_invoice": si.name}),
        )

        self.assertFalse(
            frappe.db.get_value("e-Waybill Log", {"reference_name": si.name}, "name")
        )

    @responses.activate
    def test_cancel_e_invoice(self):
        """Test for generate and cancel e-Invoice"""

        data = self.e_invoice_test_data.get("goods_item_with_ewaybill")
        self.update_doc_details(data)

        si = create_sales_invoice(**data.get("kwargs"))

        self._generate_e_invoice(data, si.name)

        self._cancel_e_invoice(si.name)

        self.assertDocumentEqual({"irn": None}, si)
        self.assertDocumentEqual({"ewaybill": None}, si)

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

    def test_validate_if_e_invoice_can_be_cancelled(self):
        """Test if e_invoice can be cancelled"""

        data = self.e_invoice_test_data.get("service_item")
        self.update_doc_details(data)

        si = create_sales_invoice(**data.get("kwargs"))

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(IRN not found)$"),
            validate_if_e_invoice_can_be_cancelled,
            si,
        )
        # ToDo: case to validate "e-Invoice can only be cancelled upto 24 hours after it is generated"

        # self._generate_e_invoice(data, si.name)

        # print(si.get_onload().get("e_invoice_info", {}).get("acknowledged_on"))

        # self.assertRaisesRegex(
        #     frappe.exceptions.ValidationError,
        #     re.compile(r"^(e-Invoice can only be cancelled.*)$"),
        #     validate_if_e_invoice_can_be_cancelled,
        #     si,
        # )

    def _generate_e_invoice(self, data, inv_name):
        responses.add(
            responses.POST,
            self.BASE_URL + "/test/ei/api/invoice",
            body=json.dumps(data.get("response_data")),
            match=[matchers.json_params_matcher(data.get("request_data"))],
            status=200,
        )

        generate_e_invoice(inv_name)

    def _cancel_e_invoice(self, invoice_no):
        si_doc = frappe.get_doc("Sales Invoice", invoice_no)

        cancel_e_waybill = self.e_invoice_test_data.get("cancel_e_waybill")
        cancel_e_waybill.get("request_data").update({"ewbNo": si_doc.ewaybill}),
        cancel_e_waybill.get("response_data").get("result").update(
            {"ewayBillNo": si_doc.ewaybill}
        )

        cancel_irn = self.e_invoice_test_data.get("cancel_e_invoice")
        cancel_irn.get("request_data").update({"Irn": si_doc.irn})
        cancel_irn.get("response_data").get("result").update({"Irn": si_doc.irn})

        responses.add(
            responses.POST,
            self.BASE_URL + "/test/ei/api/ewayapi",
            body=json.dumps(cancel_e_waybill.get("response_data")),
            match=[matchers.json_params_matcher(cancel_e_waybill.get("request_data"))],
            status=200,
        )

        responses.add(
            responses.POST,
            self.BASE_URL + "/test/ei/api/invoice/cancel",
            body=json.dumps(cancel_irn.get("response_data")),
            match=[matchers.json_params_matcher(cancel_irn.get("request_data"))],
            status=200,
        )

        values = {
            "reason": "Data Entry Mistake",
            "remark": "Data Entry Mistake",
        }

        cancel_e_invoice(si_doc.name, values)

    def update_doc_details(self, e_invoice_test_data, inv_no=None, is_return=False):
        today = format_date(frappe.utils.today(), "dd/mm/yyyy")

        e_invoice_test_data.get("response_data").get("result").update(
            {"AckDt": str(now_datetime())}
        )

        for key, value in e_invoice_test_data.get("request_data").items():
            if key == "DocDtls":
                value.update({"Dt": today})
            if key == "RefDtls":
                for inv_data in value.get("PrecDocDtls"):
                    inv_data["InvDt"] = today
                    if is_return:
                        inv_data["InvNo"] = inv_no
