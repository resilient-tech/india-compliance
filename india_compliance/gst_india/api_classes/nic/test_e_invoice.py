from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.api_classes.nic.e_invoice import (
    EInvoiceAPI,
    EnrichedEInvoiceAPI,
    StandardEInvoiceAPI,
)


class TestEInvoiceAPI(IntegrationTestCase):
    def test_create_returns_standard_in_normal_mode(self):
        mock_settings = frappe._dict(
            sandbox_mode=False, use_fallback_for_nic=False, api_secret="test-secret"
        )
        mock_settings.get_password = lambda *a, **kw: "test-secret"
        with patch.object(frappe, "get_cached_doc", return_value=mock_settings):
            with patch(
                "india_compliance.gst_india.api_classes.base.is_api_enabled",
                return_value=True,
            ):
                with patch.object(StandardEInvoiceAPI, "setup"):
                    api = EInvoiceAPI.create()

        self.assertIsInstance(api, StandardEInvoiceAPI)

    def test_create_returns_enriched_in_sandbox_mode(self):
        mock_settings = frappe._dict(
            sandbox_mode=True, use_fallback_for_nic=False, api_secret="test-secret"
        )
        mock_settings.get_password = lambda *a, **kw: "test-secret"
        with patch.object(frappe, "get_cached_doc", return_value=mock_settings):
            with patch(
                "india_compliance.gst_india.api_classes.base.is_api_enabled",
                return_value=True,
            ):
                with patch.object(EnrichedEInvoiceAPI, "setup"):
                    api = EInvoiceAPI.create()

        self.assertIsInstance(api, EnrichedEInvoiceAPI)

    def test_create_returns_enriched_when_using_fallback(self):
        mock_settings = frappe._dict(
            sandbox_mode=False, use_fallback_for_nic=True, api_secret="test-secret"
        )
        mock_settings.get_password = lambda *a, **kw: "test-secret"
        with patch.object(frappe, "get_cached_doc", return_value=mock_settings):
            with patch(
                "india_compliance.gst_india.api_classes.base.is_api_enabled",
                return_value=True,
            ):
                with patch.object(EnrichedEInvoiceAPI, "setup"):
                    api = EInvoiceAPI.create()

        self.assertIsInstance(api, EnrichedEInvoiceAPI)

    def test_validate_enable_api_raises_when_e_invoice_disabled(self):
        api = EInvoiceAPI.__new__(EInvoiceAPI)
        api.settings = frappe._dict(enable_e_invoice=False)

        with self.assertRaises(frappe.ValidationError):
            api.validate_enable_api()

    def test_validate_enable_api_succeeds_when_enabled(self):
        api = EInvoiceAPI.__new__(EInvoiceAPI)
        api.settings = frappe._dict(enable_e_invoice=True)

        api.validate_enable_api()

    def test_get_e_invoice_by_irn_calls_get_with_correct_args(self):
        api = EInvoiceAPI.__new__(EInvoiceAPI)

        with patch.object(api, "get") as mock_get:
            api.get_e_invoice_by_irn("test-irn")

        mock_get.assert_called_once_with(
            endpoint="invoice/irn", params={"irn": "test-irn"}
        )

    def test_is_ignored_error_returns_true_for_2150(self):
        api = EInvoiceAPI.__new__(EInvoiceAPI)
        response = frappe._dict(message="2150: Duplicate IRN")

        result = api.is_ignored_error(response)

        self.assertTrue(result)
        self.assertEqual(response.error_code, "2150")
        self.assertEqual(response.error_message, "2150: Duplicate IRN")

    def test_is_ignored_error_returns_true_for_2283(self):
        api = EInvoiceAPI.__new__(EInvoiceAPI)
        response = frappe._dict(
            message="2283: IRN details cannot be provided as it is generated more than 2 days ago"
        )

        result = api.is_ignored_error(response)

        self.assertTrue(result)
        self.assertEqual(response.error_code, "2283")

    def test_is_ignored_error_returns_true_for_1005(self):
        api = EInvoiceAPI.__new__(EInvoiceAPI)
        response = frappe._dict(message="1005: Invalid Token")

        result = api.is_ignored_error(response)

        self.assertTrue(result)
        self.assertEqual(response.error_code, "1005")

    def test_is_ignored_error_returns_false_for_unknown_code(self):
        api = EInvoiceAPI.__new__(EInvoiceAPI)
        response = frappe._dict(message="99999: Unknown error")

        result = api.is_ignored_error(response)

        self.assertFalse(result)

    def test_is_ignored_error_returns_false_for_empty_message(self):
        api = EInvoiceAPI.__new__(EInvoiceAPI)
        response = frappe._dict(message="")

        result = api.is_ignored_error(response)

        self.assertFalse(result)

    def test_is_ignored_error_strips_message_whitespace(self):
        api = EInvoiceAPI.__new__(EInvoiceAPI)
        response = frappe._dict(message="  2150: Duplicate IRN  ")

        result = api.is_ignored_error(response)

        self.assertTrue(result)
        self.assertEqual(response.error_code, "2150")


class TestStandardEInvoiceAPI(IntegrationTestCase):
    def test_is_ignored_error_returns_true_for_2150(self):
        api = StandardEInvoiceAPI.__new__(StandardEInvoiceAPI)
        response = frappe._dict(
            ErrorDetails=[
                frappe._dict(ErrorCode="2150", ErrorMessage="Duplicate IRN")
            ]
        )

        result = api.is_ignored_error(response)

        self.assertTrue(result)
        self.assertEqual(response.error_code, "2150")
        self.assertEqual(response.error_message, "2150: Duplicate IRN")

    def test_is_ignored_error_returns_false_when_no_error_details(self):
        api = StandardEInvoiceAPI.__new__(StandardEInvoiceAPI)
        response = frappe._dict()

        result = api.is_ignored_error(response)

        self.assertFalse(result)
