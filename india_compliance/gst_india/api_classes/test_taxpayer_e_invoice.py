from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.api_classes.taxpayer_e_invoice import EInvoiceAPI


class TestTaxpayerEInvoiceAPI(IntegrationTestCase):
    def test_setup_throws_in_sandbox_mode(self):
        api = EInvoiceAPI.__new__(EInvoiceAPI)
        api.sandbox_mode = True

        with self.assertRaises(frappe.ValidationError):
            api.setup(company_gstin="27AAAAA0000A1Z5")

    def test_setup_throws_without_company_gstin(self):
        api = EInvoiceAPI.__new__(EInvoiceAPI)
        api.sandbox_mode = False
        api.settings = frappe._dict({"credentials": []})

        with self.assertRaises(frappe.ValidationError):
            api.setup()

    def test_setup_throws_with_none_company_gstin(self):
        api = EInvoiceAPI.__new__(EInvoiceAPI)
        api.sandbox_mode = False
        api.settings = frappe._dict({"credentials": []})

        with self.assertRaises(frappe.ValidationError):
            api.setup(company_gstin=None)

    def test_setup_raises_when_credentials_not_found_even_with_doc_gstin(self):
        api = EInvoiceAPI.__new__(EInvoiceAPI)
        api.sandbox_mode = False
        api.settings = frappe._dict({"credentials": []})
        doc = frappe._dict({"company_gstin": "27AAAAA0000A1Z5", "doctype": "Sales Invoice", "name": "INV-001"})

        with self.assertRaises(frappe.ValidationError):
            api.setup(doc=doc)

    def test_get_irn_list_builds_correct_params(self):
        api = EInvoiceAPI.__new__(EInvoiceAPI)
        api.company_gstin = "27AAAAA0000A1Z5"

        with patch.object(api, "get", return_value=frappe._dict({})) as mock_get:
            api.get_irn_list(return_period="072026", supply_type="B2B")

        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args[1]
        self.assertEqual(call_kwargs["action"], "IRNLIST")
        self.assertEqual(call_kwargs["params"]["rtnprd"], "072026")
        self.assertEqual(call_kwargs["params"]["suptyp"], "B2B")
        self.assertEqual(call_kwargs["endpoint"], "einvoice")

    def test_get_irn_details_builds_correct_params(self):
        api = EInvoiceAPI.__new__(EInvoiceAPI)
        api.company_gstin = "27AAAAA0000A1Z5"

        with patch.object(api, "get", return_value=frappe._dict({})) as mock_get:
            api.get_irn_details(irn="test-irn-value")

        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args[1]
        self.assertEqual(call_kwargs["action"], "IRNDTL")
        self.assertEqual(call_kwargs["params"]["irn"], "test-irn-value")
        self.assertEqual(call_kwargs["endpoint"], "einvoice")

    def test_download_files_calls_get_files_with_filedetl(self):
        api = EInvoiceAPI.__new__(EInvoiceAPI)
        api.company_gstin = "27AAAAA0000A1Z5"

        with patch.object(api, "get_files", return_value=frappe._dict({})) as mock_get_files:
            api.download_files(return_period="072026", token="test-token")

        mock_get_files.assert_called_once_with(
            "072026", "test-token", action="FILEDETL", endpoint="einvoice", otp=None
        )
