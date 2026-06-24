import json
import re

import frappe
import responses
from erpnext.controllers.sales_and_purchase_return import make_return_doc
from frappe.tests import IntegrationTestCase, change_settings
from frappe.utils import add_to_date, get_datetime, getdate, now_datetime
from frappe.utils.data import format_date
from responses import matchers

from india_compliance.gst_india.api_classes.base import BASE_URL
from india_compliance.gst_india.overrides.test_transaction import (
    create_refund_transaction,
)
from india_compliance.gst_india.utils import load_doc
from india_compliance.gst_india.utils.e_invoice import (
    EInvoiceData,
    cancel_e_invoice,
    generate_e_invoice,
    mark_e_invoice_as_cancelled,
    mark_e_invoice_as_generated,
    validate_e_invoice_applicability,
    validate_if_e_invoice_can_be_cancelled,
)
from india_compliance.gst_india.utils.e_waybill import EWaybillData
from india_compliance.gst_india.utils.tests import (
    append_item,
    create_sales_invoice,
    enable_custom_gst_charge_types,
)


class EInvoiceTestMixin:
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
                "attach_e_waybill_print": 0,
                "apply_e_invoice_only_for_selected_companies": 0,
                "enable_retry_einv_ewb_generation": 1,
                "auto_cancel_e_invoice": 0,
                "restrict_cancel_if_e_invoice_final": 0,
            },
        )
        cls.e_invoice_test_data = frappe._dict(
            frappe.get_file_json(
                frappe.get_app_path("india_compliance", "gst_india", "data", "test_e_invoice.json")
            )
        )
        update_dates_for_test_data(cls.e_invoice_test_data)
        enable_custom_gst_charge_types()

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


class TestEInvoice(EInvoiceTestMixin, IntegrationTestCase):
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
            **test_data.get("kwargs"),
            qty=1000,
            do_not_submit=True,
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
        e_invoice_data.get_data()

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
                    "OthChrg": 0,
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
                    "OthChrg": 0,
                    "TotItemVal": 8.5,
                    "BchDtls": {"Nm": None, "ExpDt": None},
                },
            ],
        )

        total_item_wise_cgst = sum(row["CgstAmt"] for row in e_invoice_data.item_list)
        self.assertEqual(
            si.taxes[0].base_tax_amount_after_discount_amount,
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

        frappe.db.set_single_value("GST Settings", "e_invoice_applicable_from", "2021-01-01")

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(e-Invoice can only be generated.*)$"),
            EInvoiceData(si).validate_transaction,
        )

    @responses.activate
    @change_settings("GST Settings", {"use_fallback_for_nic": 1})
    def test_generate_e_invoice_with_cancelled_shipping_gstin_enriched(self):
        """Test error handling for cancelled shipping GSTIN - Enriched API (error 3029)"""

        test_data = self.e_invoice_test_data.get("gstin_error_3029_cancelled")
        si = create_sales_invoice(
            **test_data.get("kwargs"),
            qty=1000,
            is_in_state=True,
        )

        error_response = test_data.get("error_response_enriched")

        responses.add(
            responses.POST,
            BASE_URL + "/test/ei/api/invoice",
            json=error_response,
            status=200,
        )

        sync_gstin_response = test_data.get("sync_gstin_response_inactive")

        responses.add(
            responses.GET,
            BASE_URL + "/test/ei/api/master/syncgstin",
            match=[matchers.query_param_matcher({"gstin": "29AAACI1195H2ZH"})],
            json=sync_gstin_response,
            status=200,
        )

        with self.assertRaises(frappe.exceptions.ValidationError) as cm:
            generate_e_invoice(si.name)

        self.assertIn("GSTIN -29AAACI1195H2ZH is inactive or cancelled", str(cm.exception))

    @responses.activate
    @change_settings("GST Settings", {"use_fallback_for_nic": 0, "sandbox_mode": 0})
    def test_generate_e_invoice_with_cancelled_shipping_gstin_standard(self):
        """Test error handling for cancelled shipping GSTIN - Standard API (error 3029)"""

        test_data = self.e_invoice_test_data.get("gstin_error_3029_cancelled")
        si = create_sales_invoice(
            **test_data.get("kwargs"),
            qty=1000,
            is_in_state=True,
        )

        error_response = test_data.get("error_response_standard")

        responses.add(
            responses.POST,
            BASE_URL + "/standard/ei/api/invoice",
            json=error_response,
            status=200,
        )

        sync_gstin_response = test_data.get("sync_gstin_response_inactive")

        responses.add(
            responses.GET,
            BASE_URL + "/standard/ei/api/master/syncgstin",
            match=[matchers.query_param_matcher({"gstin": "29AAACI1195H2ZH"})],
            json=sync_gstin_response,
            status=200,
        )

        frappe.flags.bypass_auth = True
        try:
            with self.assertRaises(frappe.exceptions.ValidationError) as cm:
                generate_e_invoice(si.name)
        finally:
            frappe.flags.bypass_auth = False

        self.assertIn("GSTIN -29AAACI1195H2ZH is inactive or cancelled", str(cm.exception))

    @responses.activate
    def test_generate_e_invoice_with_goods_item(self):
        """Generate test e-Invoice for goods item"""
        frappe.db.set_single_value("GST Settings", {"auto_cancel_e_waybill": 0, "fetch_e_waybill_data": 0})

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
            frappe.get_doc("e-Invoice Log", {"reference_name": si.name}),
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
            frappe.get_doc("e-Invoice Log", {"reference_name": si.name}),
        )

        self.assertFalse(frappe.db.get_value("e-Waybill Log", {"reference_name": si.name}, "name"))

    @change_settings("GST Settings", {"nil_exempt_e_invoice_treatment": "Do Not Generate"})
    def test_do_not_generate_for_nil_only_invoice(self):
        """e-Invoice should be blocked for all-nil/exempt invoices when set to Do Not Generate."""
        test_data = self.e_invoice_test_data.get("nil_exempted_item")
        si = create_sales_invoice(**test_data.get("kwargs"), do_not_submit=True, is_in_state=True)
        si.submit()

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r".*e-Invoice is not applicable for this invoice as all items are non-taxable."),
            validate_e_invoice_applicability,
            si,
        )

    @responses.activate
    @change_settings("GST Settings", {"nil_exempt_e_invoice_treatment": "Generate with Other Charges"})
    def test_generate_e_invoice_with_nil_exempted_item(self):
        """Generate e-Invoice for invoice containing Nil/Exempted items."""
        test_data = self.e_invoice_test_data.get("nil_exempted_item")
        si = create_sales_invoice(**test_data.get("kwargs"), do_not_submit=True, is_in_state=True)

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
            frappe.get_doc("e-Invoice Log", {"reference_name": si.name}),
        )

        self.assertFalse(frappe.db.get_value("e-Waybill Log", {"reference_name": si.name}, "name"))

    @change_settings("GST Settings", {"nil_exempt_e_invoice_treatment": "Generate with Other Charges"})
    def test_request_data_for_nil_only_invoice_with_other_charges(self):
        """Nil-only invoice: nil items in ItemList with AssAmt=0, item-level OthChrg=value."""
        test_data = self.e_invoice_test_data.get("nil_exempted_item")
        si = create_sales_invoice(**test_data.get("kwargs"), do_not_submit=True, is_in_state=True)

        request_data = EInvoiceData(si).get_data()

        self.assertEqual(1, len(request_data["ItemList"]))

        nil_item = request_data["ItemList"][0]
        self.assertEqual(0, nil_item["AssAmt"])
        self.assertEqual(0, nil_item["TotAmt"])
        self.assertEqual(0, nil_item["UnitPrice"])
        self.assertEqual(100, nil_item["OthChrg"])
        self.assertEqual(100, nil_item["TotItemVal"])

        self.assertEqual(0, request_data["ValDtls"]["AssVal"])
        self.assertEqual(0, request_data["ValDtls"]["OthChrg"])
        self.assertEqual(100, request_data["ValDtls"]["TotInvVal"])

    @change_settings("GST Settings", {"nil_exempt_e_invoice_treatment": "Generate with Taxable Values"})
    def test_request_data_for_nil_only_invoice_with_taxable_values(self):
        """Nil-only invoice: taxable values reported in item fields when setting is enabled; AssVal = total."""
        test_data = self.e_invoice_test_data.get("nil_exempted_item")
        si = create_sales_invoice(**test_data.get("kwargs"), do_not_submit=True, is_in_state=True)

        request_data = EInvoiceData(si).get_data()

        self.assertEqual(1, len(request_data["ItemList"]))

        nil_item = request_data["ItemList"][0]
        self.assertEqual(100, nil_item["AssAmt"])
        self.assertEqual(100, nil_item["TotAmt"])
        self.assertEqual(100, nil_item["UnitPrice"])
        self.assertEqual(0, nil_item["OthChrg"])
        self.assertEqual(100, nil_item["TotItemVal"])

        self.assertEqual(100, request_data["ValDtls"]["AssVal"])
        self.assertEqual(0, request_data["ValDtls"]["OthChrg"])
        self.assertEqual(100, request_data["ValDtls"]["TotInvVal"])

    @change_settings("GST Settings", {"nil_exempt_e_invoice_treatment": "Do Not Generate"})
    def test_request_data_for_mixed_invoice_with_do_not_generate(self):
        """Mixed invoice with Do Not Generate: nil items reported as item-level OthChrg (same as Generate with Other Charges); validation only blocks an all-nil invoice."""
        test_data = self.e_invoice_test_data.get("nil_exempted_item")
        si = create_sales_invoice(**test_data.get("kwargs"), do_not_submit=True, is_in_state=True)

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

        request_data = EInvoiceData(si).get_data()

        self.assertEqual(2, len(request_data["ItemList"]))

        nil_item = next(item for item in request_data["ItemList"] if item["GstRt"] == 0)
        taxable_item = next(item for item in request_data["ItemList"] if item["GstRt"] == 12.0)

        self.assertEqual(0, nil_item["AssAmt"])
        self.assertEqual(100, nil_item["OthChrg"])
        self.assertEqual(100, nil_item["TotItemVal"])

        self.assertEqual(10, taxable_item["AssAmt"])
        self.assertEqual(0, taxable_item["OthChrg"])
        self.assertEqual(11.2, taxable_item["TotItemVal"])

        self.assertEqual(10, request_data["ValDtls"]["AssVal"])

    @change_settings("GST Settings", {"nil_exempt_e_invoice_treatment": "Generate with Other Charges"})
    def test_request_data_with_nil_exempted_item_as_other_charges(self):
        """Mixed invoice with Generate with Other Charges: nil items in ItemList with item-level OthChrg."""
        test_data = self.e_invoice_test_data.get("nil_exempted_item")
        si = create_sales_invoice(**test_data.get("kwargs"), do_not_submit=True, is_in_state=True)

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

        request_data = EInvoiceData(si).get_data()

        self.assertEqual(2, len(request_data["ItemList"]))

        nil_item = next(item for item in request_data["ItemList"] if item["GstRt"] == 0)
        taxable_item = next(item for item in request_data["ItemList"] if item["GstRt"] == 12.0)

        self.assertEqual(0, nil_item["AssAmt"])
        self.assertEqual(0, nil_item["TotAmt"])
        self.assertEqual(0, nil_item["UnitPrice"])
        self.assertEqual(100, nil_item["OthChrg"])
        self.assertEqual(100, nil_item["TotItemVal"])

        self.assertEqual(10, taxable_item["AssAmt"])
        self.assertEqual(10, taxable_item["TotAmt"])
        self.assertEqual(10, taxable_item["UnitPrice"])
        self.assertEqual(0, taxable_item["OthChrg"])
        self.assertEqual(11.2, taxable_item["TotItemVal"])

        self.assertEqual(10, request_data["ValDtls"]["AssVal"])
        self.assertEqual(0, request_data["ValDtls"]["OthChrg"])
        self.assertEqual(111, request_data["ValDtls"]["TotInvVal"])

    @change_settings("GST Settings", {"nil_exempt_e_invoice_treatment": "Generate with Taxable Values"})
    def test_request_data_with_nil_exempted_item_as_line_item(self):
        """Nil/Exempted item should be reported with taxable values when setting is enabled."""
        test_data = self.e_invoice_test_data.get("nil_exempted_item")
        si = create_sales_invoice(**test_data.get("kwargs"), do_not_submit=True, is_in_state=True)

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

        request_data = EInvoiceData(si).get_data()

        self.assertEqual(2, len(request_data["ItemList"]))

        nil_item = next(item for item in request_data["ItemList"] if item["GstRt"] == 0)
        taxable_item = next(item for item in request_data["ItemList"] if item["GstRt"] == 12.0)

        self.assertEqual(100, nil_item["AssAmt"])
        self.assertEqual(100, nil_item["TotAmt"])
        self.assertEqual(100, nil_item["UnitPrice"])
        self.assertEqual(0, nil_item["GstRt"])
        self.assertEqual(0, nil_item["IgstAmt"])
        self.assertEqual(0, nil_item["CgstAmt"])
        self.assertEqual(0, nil_item["SgstAmt"])
        self.assertEqual(0, nil_item["OthChrg"])
        self.assertEqual(100, nil_item["TotItemVal"])

        self.assertEqual(10, taxable_item["AssAmt"])
        self.assertEqual(10, taxable_item["TotAmt"])
        self.assertEqual(10, taxable_item["UnitPrice"])
        self.assertEqual(12.0, taxable_item["GstRt"])
        self.assertEqual(0.6, taxable_item["CgstAmt"])
        self.assertEqual(0.6, taxable_item["SgstAmt"])
        self.assertEqual(11.2, taxable_item["TotItemVal"])

        self.assertEqual(110, request_data["ValDtls"]["AssVal"])
        self.assertEqual(0, request_data["ValDtls"]["OthChrg"])
        self.assertEqual(111, request_data["ValDtls"]["TotInvVal"])

    def test_request_data_for_rsp_on_mrp(self):
        """Tobacco RSP ("On MRP"): tax is computed on the RSP-deemed value, but AssAmt is the
        net sale value (not the RSP), with no other charges. RSP 118 inclusive of 18% (9+9)
        on a net sale of 90 -> deemed 100, CGST/SGST 9 each, AssAmt 90, TotItemVal 108."""
        si = create_sales_invoice(
            rate=90,
            is_in_state=True,
            company_address="_Test Indian Registered Company-Billing",
            do_not_save=True,
        )
        si.items[0].gst_retail_sale_price = 118
        for tax in si.taxes:
            tax.charge_type = "On MRP"
        si.insert()

        request_data = EInvoiceData(si).get_data()
        item = request_data["ItemList"][0]

        self.assertEqual(item["AssAmt"], 90)
        self.assertEqual(item["GstRt"], 18.0)
        self.assertEqual(item["CgstAmt"], 9)
        self.assertEqual(item["SgstAmt"], 9)
        self.assertEqual(item["OthChrg"], 0)
        self.assertEqual(item["TotItemVal"], 108)

        val = request_data["ValDtls"]
        self.assertEqual(val["AssVal"], 90)
        self.assertEqual(val["OthChrg"], 0)
        self.assertEqual(val["TotInvVal"], 108)
        # NIC: TotInvVal = sum(item TotItemVal) + doc OthChrg
        total_item_val = sum(i["TotItemVal"] for i in request_data["ItemList"])
        self.assertEqual(total_item_val + val["OthChrg"], val["TotInvVal"])

    def test_request_data_for_margin_scheme(self):
        """Margin scheme ("On Margin"), GST inclusive in the margin: only the margin is
        taxable, the purchase cost surfaces as document-level OthChrg via the existing plug
        (grand_total - taxable - tax), so taxable + tax < invoice value. Sale 300, cost 182
        -> margin 118 incl 18% -> deemed 100, CGST/SGST 9 each. Item AssAmt 100, OthChrg 0,
        TotItemVal 118; doc OthChrg 182, TotInvVal 300."""
        si = create_sales_invoice(
            rate=300,
            is_in_state=True,
            company_address="_Test Indian Registered Company-Billing",
            do_not_save=True,
        )
        si.items[0].gst_purchase_price = 182
        si.items[0].allow_zero_valuation_rate = 1
        for tax in si.taxes:
            tax.charge_type = "On Margin"
            tax.included_in_print_rate = 1
        si.insert()

        request_data = EInvoiceData(si).get_data()
        item = request_data["ItemList"][0]

        self.assertEqual(item["AssAmt"], 100)
        self.assertEqual(item["GstRt"], 18.0)
        self.assertEqual(item["CgstAmt"], 9)
        self.assertEqual(item["SgstAmt"], 9)
        self.assertEqual(item["OthChrg"], 0)  # cost is reported at doc level, not the item
        self.assertEqual(item["TotItemVal"], 118)  # margin + tax

        val = request_data["ValDtls"]
        self.assertEqual(val["AssVal"], 100)
        self.assertEqual(val["OthChrg"], 182)  # purchase cost balance
        self.assertEqual(val["TotInvVal"], 300)
        self.assertLess(val["AssVal"] + val["CgstVal"] + val["SgstVal"], val["TotInvVal"])
        # NIC: TotInvVal = sum(item TotItemVal) + doc OthChrg (no double counting -> no error 2189)
        total_item_val = sum(i["TotItemVal"] for i in request_data["ItemList"])
        self.assertEqual(total_item_val + val["OthChrg"], val["TotInvVal"])

    def test_request_data_for_margin_scheme_return(self):
        """Margin scheme credit note (qty -ve): margin is negative, so Rule 32(5) levies no
        GST. The whole value rides the document-level OthChrg; the e-Invoice reconciles
        (AssVal 0, no tax)."""
        si = create_sales_invoice(
            rate=300,
            is_in_state=True,
            company_address="_Test Indian Registered Company-Billing",
            do_not_save=True,
        )
        si.items[0].gst_purchase_price = 182
        si.items[0].allow_zero_valuation_rate = 1
        for tax in si.taxes:
            tax.charge_type = "On Margin"
            tax.included_in_print_rate = 1
        si.insert()
        si.submit()

        cn = make_return_doc("Sales Invoice", si.name)
        cn.insert()

        request_data = EInvoiceData(cn).get_data()
        item = request_data["ItemList"][0]
        val = request_data["ValDtls"]

        self.assertEqual(item["AssAmt"], 0)
        self.assertEqual(item["CgstAmt"], 0)
        self.assertEqual(item["SgstAmt"], 0)
        self.assertEqual(item["OthChrg"], 0)  # whole value rides doc-level OthChrg
        self.assertEqual(val["AssVal"], 0)
        self.assertEqual(val["OthChrg"], 300)
        self.assertEqual(val["TotInvVal"], 300)
        total_item_val = sum(i["TotItemVal"] for i in request_data["ItemList"])
        self.assertEqual(total_item_val + val["OthChrg"], val["TotInvVal"])

    @change_settings("GST Settings", {"nil_exempt_e_invoice_treatment": "Generate with Taxable Values"})
    def test_margin_scheme_not_folded_by_nil_as_taxable(self):
        """The 'Generate with Taxable Values' option folds nil/exempt supplies into taxable.
        A margin line's cost rides the document-level OthChrg (not item non_taxable), so the
        fold has nothing to grab — AssVal stays the margin (100), not 100 + 182."""
        si = create_sales_invoice(
            rate=300,
            is_in_state=True,
            company_address="_Test Indian Registered Company-Billing",
            do_not_save=True,
        )
        si.items[0].gst_purchase_price = 182
        si.items[0].allow_zero_valuation_rate = 1
        for tax in si.taxes:
            tax.charge_type = "On Margin"
            tax.included_in_print_rate = 1
        si.insert()

        request_data = EInvoiceData(si).get_data()
        item = request_data["ItemList"][0]
        val = request_data["ValDtls"]

        self.assertEqual(item["AssAmt"], 100)
        self.assertEqual(item["OthChrg"], 0)
        self.assertEqual(val["AssVal"], 100)  # margin only, NOT 100 + 182
        self.assertEqual(val["OthChrg"], 182)
        self.assertEqual(val["TotInvVal"], 300)

    @responses.activate
    def test_credit_note_e_invoice_with_goods_item(self):
        """Generate test e-Invoice for returned Sales Invoices"""
        test_data = self.e_invoice_test_data.get("return_invoice")

        si = create_sales_invoice(
            item_tax_template="GST 12% - _TIRC",
            rate=7.6,
            is_in_state=True,
            do_not_submit=True,
            company_address="_Test Indian Registered Company-Billing",
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
            frappe.get_doc("e-Invoice Log", {"reference_name": credit_note.name}),
        )

        self.assertFalse(frappe.db.get_value("e-Waybill Log", {"reference_name": credit_note.name}, "name"))

    @responses.activate
    def test_debit_note_e_invoice_with_goods_item(self):
        """Generate test e-Invoice for debit note with zero quantity"""
        test_data = self.e_invoice_test_data.get("debit_invoice")
        si = create_sales_invoice(
            customer_address=test_data.get("kwargs").get("customer_address"),
            shipping_address_name=test_data.get("kwargs").get("shipping_address_name"),
            company_address=test_data.get("kwargs").get("company_address"),
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
        self.assertDictEqual(test_data.get("request_data"), EInvoiceData(debit_note).get_data())

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
            frappe.get_doc("e-Invoice Log", {"reference_name": debit_note.name}),
        )

        self.assertFalse(frappe.db.get_value("e-Waybill Log", {"reference_name": debit_note.name}, "name"))

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

        test_data.get("response_data").get("result").update({"AckDt": str(now_datetime())})

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
    def test_auto_cancel_e_invoice(self):
        """Test for auto cancel e-Invoice on cancellation of Sales Invoice"""
        frappe.db.set_single_value("GST Settings", "auto_cancel_e_invoice", 1)
        test_data = self.e_invoice_test_data.get("service_item")
        si = create_sales_invoice(
            **test_data.get("kwargs"),
            is_in_state=True,
        )
        test_data.get("response_data").get("result").update({"AckDt": str(add_to_date(days=-2))})
        # Mock response for generating irnFser
        self._mock_e_invoice_response(data=test_data)

        generate_e_invoice(si.name)

        si_doc = load_doc("Sales Invoice", si.name, "cancel")

        # Assert e-Invoice is not cancellable
        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(e-Invoice can only be cancelled.*)$"),
            validate_if_e_invoice_can_be_cancelled,
            si_doc,
        )

        # document sholud be cancelled without any error if e-Invoice is not cancellable
        si_doc.cancel()
        frappe.db.set_single_value("GST Settings", "auto_cancel_e_invoice", 0)

    @responses.activate
    def test_mark_e_invoice_as_cancelled(self):
        """Test for mark e-Invoice as cancelled"""
        frappe.db.set_single_value("GST Settings", {"auto_cancel_e_waybill": 0, "fetch_e_waybill_data": 0})

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

        cancelled_on = get_datetime("2026-06-05 11:00:00")
        values = frappe._dict(
            {
                "reason": "Others",
                "remark": "Manually deleted from GSTR-1",
                "cancelled_on": str(cancelled_on),
            }
        )

        mark_e_invoice_as_cancelled("Sales Invoice", si.name, values)
        cancelled_doc = frappe.get_doc("Sales Invoice", si.name)

        self.assertDocumentEqual(
            {"einvoice_status": "Manually Cancelled", "irn": ""},
            cancelled_doc,
        )

        self.assertTrue(frappe.get_cached_value("e-Invoice Log", si.irn, "is_cancelled"), 1)
        self.assertEqual(
            frappe.get_cached_value("e-Invoice Log", si.irn, "cancelled_on"),
            cancelled_on,
        )

    def test_mark_e_invoice_as_generated(self):
        """Dates entered by the user should be stored as-is"""
        test_data = self.e_invoice_test_data.get("goods_item_with_ewaybill")

        si = create_sales_invoice(
            **test_data.get("kwargs"),
            qty=1000,
            is_in_state=True,
        )

        # day and month both <= 12 to catch incorrect day-first parsing
        ack_dt = get_datetime("2026-06-05 13:17:16")
        irn = "manual" + frappe.generate_hash(length=58)

        mark_e_invoice_as_generated(
            si.doctype,
            si.name,
            values={
                "irn": irn,
                "ack_no": "172512345678901",
                "ack_dt": str(ack_dt),
            },
        )

        e_invoice_log = frappe.get_doc("e-Invoice Log", irn)
        self.assertEqual(e_invoice_log.acknowledged_on, ack_dt)
        self.assertEqual(e_invoice_log.acknowledgement_number, "172512345678901")
        self.assertEqual(
            frappe.db.get_value("Sales Invoice", si.name, "einvoice_status"),
            "Manually Generated",
        )

    @change_settings("GST Settings", {"nil_exempt_e_invoice_treatment": "Generate with Other Charges"})
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
        self.assertTrue(validate_e_invoice_applicability(si))

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
        frappe.db.set_single_value("GST Settings", {"auto_cancel_e_waybill": 0, "fetch_e_waybill_data": 0})

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

        si = create_sales_invoice(
            rate=1400,
            is_in_state=True,
            company_address="_Test Indian Registered Company-Billing",
        )
        self._mock_e_invoice_response(data=test_data_with_diff_value)

        # Assert if Invoice amount has changed
        self.assertRaisesRegex(
            frappe.ValidationError,
            re.compile(r"^(An e-Invoice already exists for Invoice.*)$"),
            generate_e_invoice,
            si.name,
        )

    @responses.activate
    def test_failed_e_invoice_generation(self):
        """Test error handling when e-Invoice generation fails (empty IRN)"""
        test_data = self.e_invoice_test_data.get("failed_e_invoice_generation")

        si = create_sales_invoice(
            rate=1000,
            is_in_state=True,
            company_address="_Test Indian Registered Company-Billing",
        )

        # Mock response for failed e-Invoice generation
        self._mock_e_invoice_response(data=test_data)

        # Assert that proper error is thrown when IRN is empty
        self.assertRaisesRegex(
            frappe.ValidationError,
            re.compile(r"^(e-Invoice generation failed)$"),
            generate_e_invoice,
            si.name,
        )

        # Ensure no e-Invoice Log is created
        self.assertFalse(frappe.db.get_value("e-Invoice Log", {"reference_name": si.name}, "name"))

        # Ensure Sales Invoice status is not updated
        si.reload()
        self.assertEqual(si.einvoice_status, "Failed")

    def test_handle_duplicate_irn_response_enriched_api(self):
        """Test handle_duplicate_irn_response method for Enriched API"""
        from india_compliance.gst_india.api_classes.nic.e_invoice import (
            EnrichedEInvoiceAPI,
        )

        # Create API instance without initialization to avoid setup issues
        api = EnrichedEInvoiceAPI.__new__(EnrichedEInvoiceAPI)

        # Test case 1: Result is a list (typical for enriched API duplicate IRN)
        result_list = [
            frappe._dict(
                {
                    "InfCd": "DUPIRN",
                    "Desc": {
                        "Irn": "duplicate_irn_123",
                        "AckDt": "2025-08-20 12:00:00",
                        "AckNo": "123456789",
                    },
                }
            ),
            frappe._dict(
                {
                    "InfCd": "OTHER",
                    "Desc": {"Irn": "other_irn_456", "AckDt": "2025-08-20 13:00:00"},
                }
            ),
        ]

        processed_result = api.handle_duplicate_irn_response(result_list)

        # Should return the first DUPIRN info or first item
        self.assertEqual(processed_result.Desc.get("Irn"), "duplicate_irn_123")
        self.assertEqual(processed_result.InfCd, "DUPIRN")

        # Test case 2: Result is already a dict (normal case)
        result_dict = frappe._dict({"Irn": "normal_irn_789", "AckDt": "2025-08-20 14:00:00"})

        processed_result = api.handle_duplicate_irn_response(result_dict)

        # Should return the same dict
        self.assertEqual(processed_result.Irn, "normal_irn_789")

    def test_handle_duplicate_irn_response_standard_api(self):
        """Test handle_duplicate_irn_response method for Standard API"""
        from india_compliance.gst_india.api_classes.nic.e_invoice import (
            StandardEInvoiceAPI,
        )

        # Create API instance with mock setup to avoid initialization issues
        api = StandardEInvoiceAPI.__new__(StandardEInvoiceAPI)

        # Test case 1: Empty IRN with InfoDtls containing DUPIRN
        result_with_info_dtls = frappe._dict(
            {
                "Irn": "",
                "Status": 0,
                "InfoDtls": [
                    {
                        "InfCd": "DUPIRN",
                        "Desc": {
                            "Irn": "duplicate_irn_123",
                            "AckDt": "2025-08-20 12:00:00",
                            "AckNo": "123456789",
                        },
                    },
                    {
                        "InfCd": "OTHER",
                        "Desc": {
                            "Irn": "other_irn_456",
                            "AckDt": "2025-08-20 13:00:00",
                        },
                    },
                ],
            }
        )

        processed_result = api.handle_duplicate_irn_response(result_with_info_dtls)

        # Should return the DUPIRN info from InfoDtls
        self.assertEqual(processed_result.get("InfCd"), "DUPIRN")
        self.assertEqual(processed_result.get("Desc").get("Irn"), "duplicate_irn_123")

        # Test case 2: Empty IRN with InfoDtls but no DUPIRN
        result_no_dupirn = frappe._dict(
            {
                "Irn": "",
                "Status": 0,
                "InfoDtls": [
                    {
                        "InfCd": "OTHER",
                        "Desc": {
                            "Irn": "other_irn_789",
                            "AckDt": "2025-08-20 15:00:00",
                        },
                    }
                ],
            }
        )

        processed_result = api.handle_duplicate_irn_response(result_no_dupirn)

        # Should return the first item from InfoDtls
        self.assertEqual(processed_result.get("InfCd"), "OTHER")
        self.assertEqual(processed_result.get("Desc").get("Irn"), "other_irn_789")

        # Test case 3: Normal result with IRN (no processing needed)
        result_normal = frappe._dict({"Irn": "normal_irn_999", "AckDt": "2025-08-20 16:00:00", "Status": 1})

        processed_result = api.handle_duplicate_irn_response(result_normal)

        # Should return the same result unchanged
        self.assertEqual(processed_result.Irn, "normal_irn_999")
        self.assertEqual(processed_result.Status, 1)

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    @change_settings("System Settings", {"currency_precision": 3})
    def test_refund_transaction_invoice_total(self):
        """Test for e-Invoice generation for Refund Transaction"""

        si = create_refund_transaction()
        si.items[0].rate = 100.25
        si.save()

        data = EInvoiceData(si).get_data()

        self.assertEqual(data.get("ValDtls").get("TotInvVal"), 118.04)
        self.assertEqual(data.get("ValDtls").get("OthChrg"), 0)
        self.assertEqual(data.get("ValDtls").get("Discount"), 0)
        self.assertEqual(data.get("ValDtls").get("IgstVal"), 18.04)

    @responses.activate
    def test_cancellation_when_e_invoice_not_cancellable(self):
        """
        Test that a Sales Invoice cannot be cancelled if the associated e-Invoice is not cancellable configurable as per GST settings.
        """
        # Enable Setting
        frappe.db.set_single_value("GST Settings", "restrict_cancel_if_e_invoice_final", 1)

        test_data = self.e_invoice_test_data.get("service_item")
        si = create_sales_invoice(
            **test_data.get("kwargs"),
            is_in_state=True,
        )
        test_data.get("response_data").get("result").update({"AckDt": str(add_to_date(days=-2))})

        # Mock response for generating irn
        self._mock_e_invoice_response(data=test_data)

        generate_e_invoice(si.name)
        si.reload()

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(This document cannot be cancelled because the associated e-Invoice.*)$"),
            si.cancel,
        )

        # Disable Setting
        frappe.db.set_single_value("GST Settings", "restrict_cancel_if_e_invoice_final", 0)
        si.reload()
        si.cancel()

    def _cancel_e_invoice(self, invoice_no):
        values = frappe._dict({"reason": "Data Entry Mistake", "remark": "Data Entry Mistake"})
        doc = load_doc("Sales Invoice", invoice_no, "cancel")

        # Prepared e_waybill cancel data
        cancel_e_waybill = self.e_invoice_test_data.get("cancel_e_waybill")
        cancel_e_waybill.get("response_data").get("result").update({"ewayBillNo": doc.ewaybill})

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


def update_dates_for_test_data(test_data):
    """Update test data for e-invoice and e-waybill"""
    today = format_date(frappe.utils.today(), "dd/mm/yyyy")
    current_datetime = now_datetime().strftime("%Y-%m-%d %H:%M:%S")
    valid_upto = add_to_date(getdate(), days=1).strftime("%Y-%m-%d %I:%M:%S %p")

    for value in test_data.values():
        if not (value.get("response_data") or value.get("request_data")):
            continue

        response_request = value.get("request_data") if isinstance(value.get("request_data"), dict) else {}
        response_result = value.get("response_data").get("result") if value.get("response_data") else {}

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
