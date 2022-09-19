import json
import re

import responses
from responses import matchers

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils.data import format_date

from india_compliance.gst_india.utils.e_invoice import (
    cancel_e_invoice,
    generate_e_invoice,
    validate_e_invoice_applicability,
)
from india_compliance.gst_india.utils.tests import create_sales_invoice


class TestEInvoice(FrappeTestCase):
    BASE_URL = "https://asp.resilient.tech"

    @classmethod
    def setUpClass(cls):
        pass

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()

    @classmethod
    def setUp(cls):
        frappe.db.set_value(
            "GST Settings",
            "GST Settings",
            {
                "enable_api": 1,
                "enable_e_invoice": 1,
                "auto_generate_e_invoice": 0,
                "enable_e_waybill": 1,
            },
        )
        cls.e_invoice_test_data = frappe.get_file_json(
            frappe.get_app_path("india_compliance", "tests", "e_invoice_test_data.json")
        )

    @classmethod
    def tearDown(cls):
        frappe.db.set_value(
            "GST Settings",
            "GST Settings",
            {
                "enable_api": 0,
                "enable_e_invoice": 0,
                "auto_generate_e_invoice": 1,
                "enable_e_waybill": 0,
            },
        )

    @responses.activate
    def test_generate_e_invoice_with_goods_item(self):
        """Generate test e-Invoice for goods item"""
        data = self.e_invoice_test_data.get("goods_item_with_ewaybill")
        self.update_doc_details(data.get("request_data"))

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
        self.update_doc_details(data.get("request_data"))

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
        data = self.e_invoice_test_data.get("return_invoice")

        si = create_sales_invoice(
            customer_address="_Test Registered Customer-Billing",
            shipping_address_name="_Test Registered Customer-Billing",
        )

        self.update_doc_details(data.get("request_data"), inv_no=si.name)

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
        data = self.e_invoice_test_data.get("debit_invoice")
        self.update_doc_details(data.get("request_data"))

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
        data = self.e_invoice_test_data.get("goods_item_with_ewaybill")
        self.update_doc_details(data.get("request_data"))

        si = create_sales_invoice(**data.get("kwargs"))
        cancel_values = self.e_invoice_test_data.get("cancel_invoice")

        values = {
            "reason": "Data Entry Mistake",
            "remark": "Data Entry Mistake",
        }
        responses.add(
            responses.POST,
            self.BASE_URL + "/test/ei/api/invoice/cancel",
            body=json.dumps(data.get("response_data")),
            match=[matchers.json_params_matcher(cancel_values.get("request_data"))],
            status=200,
        )

        cancel_e_invoice(si.name, values)

        self.assertFalse(frappe.db.get_value("Sales Invoice", si.name, "irn"))
        self.assertFalse(frappe.db.get_value("Sales Invoice", si.name, "ewaybill"))

    # def test_get_data(self):
    #     si = create_sales_invoice()
    #     self.assertRaisesRegex(
    #         frappe.exceptions.ValidationError,
    #         re.compile(r"^(e-Invoice can only be generated for upto.*)$"),
    #         EInvoiceData(si).get_data(),
    #         si,
    #     )

    def test_validate_e_invoice_applicability(self):
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

    def _generate_e_invoice(self, data, inv_name):
        responses.add(
            responses.POST,
            self.BASE_URL + "/test/ei/api/invoice",
            body=json.dumps(data.get("response_data")),
            match=[matchers.json_params_matcher(data.get("request_data"))],
            status=200,
        )

        generate_e_invoice(inv_name)

    def update_doc_details(self, request_data, inv_no=None):
        today = format_date(frappe.utils.today(), "dd/mm/yyyy")
        for key, value in request_data.items():
            if key == "DocDtls":
                value.update({"Dt": today})
            if key == "RefDtls":
                for inv_data in value.get("PrecDocDtls"):
                    inv_data["InvDt"] = today
                    if inv_no:
                        inv_data["InvNo"] = inv_no
