import json
import re

import responses
from responses import matchers

import frappe
from frappe.tests.utils import FrappeTestCase, change_settings
from frappe.utils import add_to_date, get_datetime, getdate, now_datetime
from frappe.utils.data import format_date

from india_compliance.gst_india.api_classes.base import BASE_URL
from india_compliance.gst_india.utils import load_doc
from india_compliance.gst_india.utils.e_invoice import (
    EInvoiceData,
    cancel_e_invoice,
    generate_e_invoice,
    validate_e_invoice_applicability,
    validate_if_e_invoice_can_be_cancelled,
)
from india_compliance.gst_india.utils.e_waybill import EWaybillData
from india_compliance.gst_india.utils.tests import create_sales_invoice


class TestEInvoice(FrappeTestCase):
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
        cls.e_invoice_test_data = frappe._dict(
            frappe.get_file_json(
                frappe.get_app_path(
                    "india_compliance", "gst_india", "data", "test_e_invoice.json"
                )
            )
        )
        update_dates_for_test_data(cls.e_invoice_test_data)

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
        si.submit()

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

        # Assert if request data given in Json
        self.assertDictEqual(test_data.get("request_data"), EInvoiceData(si).get_data())

        # Mock response for generating irn
        self._mock_e_invoice_response(data=test_data)

        generate_e_invoice(si.name)

        # Assert if Integration Request Log generated
        self.assertDocumentEqual(
            {
                "output": frappe.as_json(test_data.get("response_data"), indent=4),
            },
            frappe.get_doc(
                "Integration Request",
                {"reference_doctype": "Sales Invoice", "reference_docname": si.name},
            ),
        )

        # Assert if Sales Doc updated
        self.assertDocumentEqual(
            {
                "irn": test_data.get("response_data").get("result").get("Irn"),
                "ewaybill": test_data.get("response_data").get("result").get("EwbNo"),
                "einvoice_status": "Generated",
            },
            frappe.get_doc("Sales Invoice", si.name),
        )

        self.assertDocumentEqual(
            {"name": test_data.get("response_data").get("result").get("Irn")},
            frappe.get_doc("e-Invoice Log", {"sales_invoice": si.name}),
        )
        self.assertDocumentEqual(
            {"name": test_data.get("response_data").get("result").get("EwbNo")},
            frappe.get_doc("e-Waybill Log", {"reference_name": si.name}),
        )

    @responses.activate
    def test_generate_e_invoice_with_service_item(self):
        """Generate test e-Invoice for Service Item"""
        test_data = self.e_invoice_test_data.get("service_item")
        si = create_sales_invoice(**test_data.get("kwargs"))

        # Assert if request data given in Json
        self.assertDictEqual(test_data.get("request_data"), EInvoiceData(si).get_data())

        # Mock response for generating irn
        self._mock_e_invoice_response(data=test_data)

        generate_e_invoice(si.name)

        # Assert if Integration Request Log generated
        self.assertDocumentEqual(
            {
                "output": frappe.as_json(test_data.get("response_data"), indent=4),
            },
            frappe.get_doc(
                "Integration Request",
                {"reference_doctype": "Sales Invoice", "reference_docname": si.name},
            ),
        )

        # Assert if Sales Doc updated
        self.assertDocumentEqual(
            {
                "irn": test_data.get("response_data").get("result").get("Irn"),
                "einvoice_status": "Generated",
            },
            frappe.get_doc("Sales Invoice", si.name),
        )

        self.assertDocumentEqual(
            {"name": test_data.get("response_data").get("result").get("Irn")},
            frappe.get_doc("e-Invoice Log", {"sales_invoice": si.name}),
        )

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

        for data in test_data.get("request_data").get("RefDtls").get("PrecDocDtls"):
            data.update(
                {
                    "InvDt": format_date(si.posting_date, "dd/mm/yyyy"),
                    "InvNo": si.name,
                }
            )

        return_si = create_sales_invoice(
            **test_data.get("kwargs"),
        )

        # Assert if request data given in Json
        self.assertDictEqual(
            test_data.get("request_data"),
            EInvoiceData(frappe.get_doc("Sales Invoice", return_si.name)).get_data(),
        )

        # Mock response for generating irn
        self._mock_e_invoice_response(data=test_data)

        generate_e_invoice(return_si.name)

        # Assert if Integration Request Log generated
        self.assertDocumentEqual(
            {
                "output": frappe.as_json(test_data.get("response_data"), indent=4),
            },
            frappe.get_doc(
                "Integration Request",
                {
                    "reference_doctype": "Sales Invoice",
                    "reference_docname": return_si.name,
                },
            ),
        )

        # Assert if Sales Doc updated
        self.assertDocumentEqual(
            {
                "irn": test_data.get("response_data").get("result").get("Irn"),
                "einvoice_status": "Generated",
            },
            frappe.get_doc("Sales Invoice", return_si.name),
        )

        self.assertDocumentEqual(
            {"name": test_data.get("response_data").get("result").get("Irn")},
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

        # Assert if request data given in Json
        self.assertDictEqual(
            test_data.get("request_data"), EInvoiceData(debit_note).get_data()
        )

        # Mock response for generating irn
        self._mock_e_invoice_response(data=test_data)

        generate_e_invoice(debit_note.name)

        # Assert if Integration Request Log generated
        self.assertDocumentEqual(
            {
                "output": frappe.as_json(test_data.get("response_data"), indent=4),
            },
            frappe.get_doc(
                "Integration Request",
                {
                    "reference_doctype": "Sales Invoice",
                    "reference_docname": debit_note.name,
                },
            ),
        )

        # Assert if Sales Doc updated
        self.assertDocumentEqual(
            {
                "irn": test_data.get("response_data").get("result").get("Irn"),
                "einvoice_status": "Generated",
            },
            frappe.get_doc("Sales Invoice", debit_note.name),
        )

        self.assertDocumentEqual(
            {"name": test_data.get("response_data").get("result").get("Irn")},
            frappe.get_doc("e-Invoice Log", {"sales_invoice": debit_note.name}),
        )

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

        test_data.get("response_data").get("result").update(
            {"AckDt": str(now_datetime())}
        )

        # Assert if request data given in Json
        self.assertDictEqual(test_data.get("request_data"), EInvoiceData(si).get_data())

        # Mock response for generating irn
        self._mock_e_invoice_response(data=test_data)

        generate_e_invoice(si.name)

        si_doc = load_doc("Sales Invoice", si.name, "cancel")
        si_doc.get_onload().get("e_invoice_info", {}).update({"acknowledged_on": None})

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(e-Invoice can only be cancelled.*)$"),
            validate_if_e_invoice_can_be_cancelled,
            si_doc,
        )

        cancelled_doc = self._cancel_e_invoice(si.name)

        self.assertDocumentEqual(
            {"einvoice_status": "Cancelled", "irn": ""},
            cancelled_doc,
        )
        self.assertDocumentEqual({"ewaybill": ""}, cancelled_doc)

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

    def _cancel_e_invoice(self, invoice_no):
        values = frappe._dict(
            {"reason": "Data Entry Mistake", "remark": "Data Entry Mistake"}
        )
        doc = load_doc("Sales Invoice", invoice_no, "cancel")

        # Prepared e_waybill cancel data
        cancel_e_waybill = self.e_invoice_test_data.get("cancel_e_waybill")
        cancel_e_waybill.get("response_data").get("result").update(
            {"ewayBillNo": doc.ewaybill}
        )

        # Assert for Mock request data
        self.assertDictEqual(
            cancel_e_waybill.get("request_data"),
            EWaybillData(doc).get_data_for_cancellation(values),
        )

        # Prepared e_invoice cancel data
        cancel_irn_test_data = self.e_invoice_test_data.get("cancel_e_invoice")
        cancel_irn_test_data.get("response_data").get("result").update({"Irn": doc.irn})

        # Assert for Mock request data
        self.assertTrue(
            cancel_e_waybill.get("request_data"),
        )

        # Mock response for cancel e_waybill
        self._mock_e_invoice_response(
            data=cancel_e_waybill,
            api="ei/api/ewayapi",
        )

        # Mock response for cancel e_invoice
        self._mock_e_invoice_response(
            data=cancel_irn_test_data,
            api="ei/api/invoice/cancel",
        )

        cancel_e_invoice(doc.name, values=values)
        return frappe.get_doc("Sales Invoice", doc.name)

    def _mock_e_invoice_response(self, data, api="ei/api/invoice"):
        """Mock response for e-Invoice API"""
        url = BASE_URL + "/test/" + api

        responses.add(
            responses.POST,
            url,
            body=json.dumps(data.get("response_data")),
            match=[matchers.json_params_matcher(data.get("request_data"))],
            status=200,
        )


def update_dates_for_test_data(test_data):
    """Update test data for e-invoice and e-waybill"""
    today = format_date(frappe.utils.today(), "dd/mm/yyyy")
    now = now_datetime().strftime("%Y-%m-%d %H:%M:%S")
    validity = add_to_date(getdate(), days=1).strftime("%Y-%m-%d %I:%M:%S %p")

    # Update test data for goods_item_with_ewaybill
    goods_item = test_data.get("goods_item_with_ewaybill")
    goods_item.get("response_data").get("result").update(
        {
            "EwbDt": now,
            "EwbValidTill": validity,
        }
    )

    # Update Document Date in given test data
    for key in (
        "goods_item_with_ewaybill",
        "service_item",
        "return_invoice",
        "debit_invoice",
    ):
        test_data.get(key).get("request_data").get("DocDtls")["Dt"] = today
        test_data.get(key).get("response_data").get("result")["AckDt"] = now

    response = test_data.cancel_e_waybill.get("response_data")
    response.get("result")["cancelDate"] = now_datetime().strftime(
        "%d/%m/%Y %I:%M:%S %p"
    )

    response = test_data.cancel_e_invoice.get("response_data")
    response.get("result")["CancelDate"] = now
