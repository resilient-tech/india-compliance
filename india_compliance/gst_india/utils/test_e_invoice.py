import json
import re

import responses
from responses import matchers

import frappe
from frappe.tests.utils import FrappeTestCase, change_settings
from frappe.utils import add_to_date, get_datetime, getdate, now_datetime
from frappe.utils.data import format_date
from erpnext.controllers.sales_and_purchase_return import make_return_doc

from india_compliance.gst_india.api_classes.base import BASE_URL
from india_compliance.gst_india.utils import load_doc
from india_compliance.gst_india.utils.e_invoice import (
    EInvoiceData,
    cancel_e_invoice,
    generate_e_invoice,
    mark_e_invoice_as_cancelled,
    validate_e_invoice_applicability,
    validate_if_e_invoice_can_be_cancelled,
)
from india_compliance.gst_india.utils.e_waybill import EWaybillData
from india_compliance.gst_india.utils.tests import append_item, create_sales_invoice


class TestEInvoice(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.db.set_single_value(
            "GST Settings",
            {
                "enable_api": 1,
                "enable_e_invoice": 1,
                "auto_generate_e_waybill": 0,
                "auto_generate_e_invoice": 0,
                "enable_e_waybill": 1,
                "fetch_e_waybill_data": 0,
                "apply_e_invoice_only_for_selected_companies": 0,
                "enable_retry_einv_ewb_generation": 1,
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

    def test_request_data_for_different_shipping_dispatch_address(self):
        test_data = self.e_invoice_test_data.goods_item_with_ewaybill
        si = create_sales_invoice(
            **test_data.get("kwargs"),
            qty=1000,
            do_not_submit=True,
            is_in_state=True,
        )

        self.assertDictEqual(
            test_data.get("request_data"),
            EInvoiceData(si).get_data(),
        )

        si.update(
            {
                "dispatch_address_name": "_Test Indian Registered Company-Shipping",
                "shipping_address_name": "_Test Registered Customer-Billing-1",
            }
        )
        si.save()

        self.assertDictEqual(
            test_data.get("request_data")
            | self.e_invoice_test_data.dispatch_details
            | self.e_invoice_test_data.shipping_details,
            EInvoiceData(si).get_data(),
        )

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_request_data_for_foreign_transactions(self):
        test_data = self.e_invoice_test_data.foreign_transaction
        si = create_sales_invoice(
            **test_data.get("kwargs"), qty=1000, do_not_submit=True
        )
        si.update(
            {
                "shipping_bill_number": "1234",
                "shipping_bill_date": frappe.utils.today(),
                "port_code": "INABG1",
            }
        )

        self.assertDictEqual(
            test_data.get("request_data"),
            EInvoiceData(si).get_data(),
        )

    def test_progressive_item_tax_amount(self):
        test_data = self.e_invoice_test_data.goods_item_with_ewaybill

        si = create_sales_invoice(
            **test_data.get("kwargs"),
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

        e_invoice_data = EInvoiceData(si)
        e_invoice_data.set_item_list()

        self.assertListEqual(
            e_invoice_data.item_list,
            [
                {
                    "SlNo": "1",
                    "PrdDesc": "Test Trading Goods 1",
                    "IsServc": "N",
                    "HsnCd": "61149090",
                    "Barcde": None,
                    "Unit": "NOS",
                    "Qty": 1.0,
                    "UnitPrice": 7.6,
                    "TotAmt": 7.6,
                    "Discount": 0,
                    "AssAmt": 7.6,
                    "PrdSlNo": "",
                    "GstRt": 12.0,
                    "IgstAmt": 0,
                    "CgstAmt": 0.46,
                    "SgstAmt": 0.46,
                    "CesRt": 0,
                    "CesAmt": 0,
                    "CesNonAdvlAmt": 0,
                    "TotItemVal": 8.52,
                    "BchDtls": {"Nm": None, "ExpDt": None},
                },
                {
                    "SlNo": "2",
                    "PrdDesc": "Test Trading Goods 1",
                    "IsServc": "N",
                    "HsnCd": "61149090",
                    "Barcde": None,
                    "Unit": "NOS",
                    "Qty": 1.0,
                    "UnitPrice": 7.6,
                    "TotAmt": 7.6,
                    "Discount": 0,
                    "AssAmt": 7.6,
                    "PrdSlNo": "",
                    "GstRt": 12.0,
                    "IgstAmt": 0,
                    "CgstAmt": 0.45,
                    "SgstAmt": 0.45,
                    "CesRt": 0,
                    "CesAmt": 0,
                    "CesNonAdvlAmt": 0,
                    "TotItemVal": 8.5,
                    "BchDtls": {"Nm": None, "ExpDt": None},
                },
            ],
        )

        total_item_wise_cgst = sum(row["CgstAmt"] for row in e_invoice_data.item_list)
        self.assertEqual(
            si.taxes[0].tax_amount,
            total_item_wise_cgst,
        )

        self.assertEqual(
            EInvoiceData(si).get_data().get("ValDtls").get("CgstVal"),
            total_item_wise_cgst,
        )

    @change_settings("Selling Settings", {"allow_multiple_items": 1})
    def test_validate_transaction(self):
        """Validation test for more than 1000 items in sales invoice"""
        si = create_sales_invoice(do_not_submit=True, is_in_state=True)
        item_row = si.get("items")[0]

        for _ in range(0, 1000):
            si.append(
                "items",
                {
                    "item_code": item_row.item_code,
                    "qty": item_row.qty,
                    "rate": item_row.rate,
                },
            )
        si.save()

        frappe.db.set_single_value(
            "GST Settings", "e_invoice_applicable_from", "2021-01-01"
        )

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(e-Invoice can only be generated.*)$"),
            EInvoiceData(si).validate_transaction,
        )

    @responses.activate
    def test_generate_e_invoice_with_goods_item(self):
        """Generate test e-Invoice for goods item"""
        test_data = self.e_invoice_test_data.get("goods_item_with_ewaybill")

        si = create_sales_invoice(
            **test_data.get("kwargs"),
            qty=1000,
            is_in_state=True,
        )

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
        si = create_sales_invoice(
            **test_data.get("kwargs"),
            is_in_state=True,
        )

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
    def test_generate_e_invoice_with_nil_exempted_item(self):
        """Generate test e-Invoice for nil/exempted items Item"""

        test_data = self.e_invoice_test_data.get("nil_exempted_item")
        si = create_sales_invoice(
            **test_data.get("kwargs"), do_not_submit=True, is_in_state=True
        )

        append_item(
            si,
            frappe._dict(
                rate=10,
                item_tax_template="GST 12% - _TIRC",
                uom="Nos",
                gst_hsn_code="61149090",
                gst_treatment="Taxable",
            ),
        )
        si.save()
        si.submit()

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
    def test_credit_note_e_invoice_with_goods_item(self):
        """Generate test e-Invoice for returned Sales Invoices"""
        test_data = self.e_invoice_test_data.get("return_invoice")

        si = create_sales_invoice(
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

        for data in test_data.get("request_data").get("RefDtls").get("PrecDocDtls"):
            data.update(
                {
                    "InvDt": format_date(si.posting_date, "dd/mm/yyyy"),
                    "InvNo": si.name,
                }
            )

        credit_note = make_return_doc("Sales Invoice", si.name)
        credit_note.save()
        credit_note.submit()

        # Assert if request data given in Json
        self.assertDictEqual(
            test_data.get("request_data"),
            EInvoiceData(frappe.get_doc("Sales Invoice", credit_note.name)).get_data(),
        )

        # Mock response for generating irn
        self._mock_e_invoice_response(data=test_data)

        generate_e_invoice(credit_note.name)

        # Assert if Integration Request Log generated
        self.assertDocumentEqual(
            {
                "output": frappe.as_json(test_data.get("response_data"), indent=4),
            },
            frappe.get_doc(
                "Integration Request",
                {
                    "reference_doctype": "Sales Invoice",
                    "reference_docname": credit_note.name,
                },
            ),
        )

        # Assert if Sales Doc updated
        self.assertDocumentEqual(
            {
                "irn": test_data.get("response_data").get("result").get("Irn"),
                "einvoice_status": "Generated",
            },
            frappe.get_doc("Sales Invoice", credit_note.name),
        )

        self.assertDocumentEqual(
            {"name": test_data.get("response_data").get("result").get("Irn")},
            frappe.get_doc("e-Invoice Log", {"sales_invoice": credit_note.name}),
        )

        self.assertFalse(
            frappe.db.get_value(
                "e-Waybill Log", {"reference_name": credit_note.name}, "name"
            )
        )

    @responses.activate
    def test_debit_note_e_invoice_with_goods_item(self):
        """Generate test e-Invoice for debit note with zero quantity"""
        test_data = self.e_invoice_test_data.get("debit_invoice")
        si = create_sales_invoice(
            customer_address=test_data.get("kwargs").get("customer_address"),
            shipping_address_name=test_data.get("kwargs").get("shipping_address_name"),
            is_in_state=True,
        )

        test_data.get("kwargs").update({"return_against": si.name})
        debit_note = create_sales_invoice(
            **test_data.get("kwargs"),
            do_not_submit=True,
            is_in_state=True,
        )

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

        si = create_sales_invoice(**test_data.get("kwargs"), qty=1000, is_in_state=True)

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

    @responses.activate
    def test_mark_e_invoice_as_cancelled(self):
        """Test for mark e-Invoice as cancelled"""
        test_data = self.e_invoice_test_data.get("goods_item_with_ewaybill")

        si = create_sales_invoice(
            **test_data.get("kwargs"),
            qty=1000,
            is_in_state=True,
        )

        # Mock response for generating irn
        self._mock_e_invoice_response(data=test_data)

        generate_e_invoice(si.name)
        si.reload()
        si.cancel()

        values = frappe._dict(
            {"reason": "Others", "remark": "Manually deleted from GSTR-1"}
        )

        mark_e_invoice_as_cancelled("Sales Invoice", si.name, values)
        cancelled_doc = frappe.get_doc("Sales Invoice", si.name)

        self.assertDocumentEqual(
            {"einvoice_status": "Manually Cancelled", "irn": ""},
            cancelled_doc,
        )

        self.assertTrue(
            frappe.get_cached_value("e-Invoice Log", si.irn, "is_cancelled"), 1
        )

    def test_validate_e_invoice_applicability(self):
        """Test if e_invoicing is applicable"""

        si = create_sales_invoice(
            customer="_Test Registered Customer",
            gst_category="Registered Regular",
            do_not_submit=True,
            is_in_state=True,
        )

        si.billing_address_gstin = "24AAQCA8719H1ZC"

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(e-Invoice is not applicable .* company and billing GSTIN)$"),
            validate_e_invoice_applicability,
            si,
        )

        si.update(
            {
                "customer": "_Test Unregistered Customer",
                "gst_category": "Unregistered",
                "billing_address_gstin": "",
            }
        )

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(e-Invoice is not applicable for B2C invoices)$"),
            validate_e_invoice_applicability,
            si,
        )

        si.update(
            {
                "gst_category": "Registered Regular",
                "customer": "_Test Registered Customer",
                "billing_address_gstin": "24AANFA2641L1ZF",
                "irn": "706daeccda0ef6f818da78f3a2a05a1288731057373002289b46c3229289a2e7",
            }
        )

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(e-Invoice has already been generated .*)$"),
            validate_e_invoice_applicability,
            si,
        )

        si.irn = ""

        si.items = []
        append_item(
            si,
            frappe._dict(
                item_code="_Test Nil Rated Item",
                item_name="_Test Nil Rated Item",
                gst_hsn_code="61149090",
                gst_treatment="Nil-Rated",
            ),
        )
        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(
                r"^(e-Invoice is not applicable for invoice with only Nil-Rated/Exempted items*)$"
            ),
            validate_e_invoice_applicability,
            si,
        )

        append_item(
            si,
            frappe._dict(
                rate=10,
                item_tax_template="GST 12% - _TIRC",
                uom="Nos",
                gst_hsn_code="61149090",
                gst_treatment="Taxable",
            ),
        )
        frappe.db.set_single_value("GST Settings", "enable_e_invoice", 0)

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(e-Invoice is not enabled in GST Settings)$"),
            validate_e_invoice_applicability,
            si,
        )

        frappe.db.set_single_value(
            "GST Settings",
            {
                "enable_e_invoice": 1,
                "apply_e_invoice_only_for_selected_companies": 0,
                "e_invoice_applicable_from": "2045-05-18",
            },
        )

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(e-Invoice is not applicable for invoices before.*)$"),
            validate_e_invoice_applicability,
            si,
        )

        gst_settings = frappe.get_cached_doc("GST Settings")
        gst_settings.update(
            {
                "apply_e_invoice_only_for_selected_companies": 1,
                "e_invoice_applicable_companies": [
                    {
                        "company": si.company,
                        "applicable_from": "2045-05-18",
                    },
                ],
            },
        )

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(e-Invoice is not applicable for invoices before.*)$"),
            validate_e_invoice_applicability,
            si,
        )

        si.company = "_Test Foreign Company"

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(e-Invoice is not applicable for company.*)$"),
            validate_e_invoice_applicability,
            si,
        )

        frappe.db.set_single_value(
            "GST Settings",
            {
                "e_invoice_applicable_from": str(get_datetime()),
                "apply_e_invoice_only_for_selected_companies": 0,
            },
        )

    @responses.activate
    def test_invoice_update_after_submit(self):
        test_data = self.e_invoice_test_data.get("goods_item_with_ewaybill")

        si = create_sales_invoice(**test_data.get("kwargs"), qty=1000, is_in_state=True)
        self._mock_e_invoice_response(data=test_data)
        generate_e_invoice(si.name)

        doc = load_doc("Sales Invoice", si.name, "submit")

        doc.group_same_items = True
        doc.save()

        self.assertEqual(
            frappe.parse_json(frappe.message_log[-1]).get("message"),
            "You have already generated e-Waybill/e-Invoice for this document."
            " This could result in mismatch of item details in e-Waybill/e-Invoice with print format.",
        )

    @responses.activate
    def test_e_invoice_for_duplicate_irn(self):
        test_data = self.e_invoice_test_data.get("goods_item_with_ewaybill")

        si = create_sales_invoice(
            **test_data.get("kwargs"),
            qty=1000,
            is_in_state=True,
        )

        # Mock response for generating irn
        self._mock_e_invoice_response(data=test_data)
        generate_e_invoice(si.name)

        test_data_with_diff_value = self.e_invoice_test_data.get("duplicate_irn")

        si = create_sales_invoice(rate=1400, is_in_state=True)
        self._mock_e_invoice_response(data=test_data_with_diff_value)

        # Assert if Invoice amount has changed
        self.assertRaisesRegex(
            frappe.ValidationError,
            re.compile(r"^(e-Invoice is already available against Invoice.*)$"),
            generate_e_invoice,
            si.name,
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

        # Mock get e_invoice by IRN response
        data = self.e_invoice_test_data.get("get_e_invoice_by_irn")

        responses.add(
            responses.GET,
            url + "/irn",
            body=json.dumps(data.get("response_data")),
            match=[matchers.query_string_matcher(data.get("request_data"))],
            status=200,
        )


def update_dates_for_test_data(test_data):
    """Update test data for e-invoice and e-waybill"""
    today = format_date(frappe.utils.today(), "dd/mm/yyyy")
    current_datetime = now_datetime().strftime("%Y-%m-%d %H:%M:%S")
    valid_upto = add_to_date(getdate(), days=1).strftime("%Y-%m-%d %I:%M:%S %p")

    for value in test_data.values():
        if not (value.get("response_data") or value.get("request_data")):
            continue

        response_request = (
            value.get("request_data")
            if isinstance(value.get("request_data"), dict)
            else {}
        )
        response_result = (
            value.get("response_data").get("result")
            if value.get("response_data")
            else {}
        )

        # Handle Duplicate IRN test data
        if isinstance(response_result, list):
            response_result = response_result[0].get("Desc")

        for k in response_request:
            if k == "DocDtls":
                response_request[k]["Dt"] = today
            elif k == "ExpDtls":
                response_request[k]["ShipBDt"] = today

        for k in response_result:
            if k == "EwbDt":
                response_result[k] = current_datetime
            elif k == "EwbValidTill":
                response_result[k] = valid_upto
            elif k == "AckDt":
                response_result[k] = current_datetime
            elif k == "cancelDate":
                response_result[k] = now_datetime().strftime("%d/%m/%Y %I:%M:%S %p")
            elif k == "CancelDate":
                response_result[k] = current_datetime
