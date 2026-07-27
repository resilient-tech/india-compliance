from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.api_classes.public import PublicAPI


class TestPublicAPI(IntegrationTestCase):
    def test_setup_raises_in_sandbox_mode(self):
        api = PublicAPI.__new__(PublicAPI)
        api.sandbox_mode = True

        with self.assertRaises(frappe.ValidationError):
            api.setup()

    def test_setup_adds_requestid_to_default_headers(self):
        api = PublicAPI.__new__(PublicAPI)
        api.sandbox_mode = False
        api.default_headers = {}
        api.default_log_values = {}

        with patch.object(api, "generate_request_id", return_value="IC-test"):
            api.setup()

        self.assertEqual(api.default_headers["requestid"], "IC-test")

    def test_setup_updates_log_values_with_doc(self):
        api = PublicAPI.__new__(PublicAPI)
        api.sandbox_mode = False
        api.default_headers = {}
        api.default_log_values = {}
        doc = frappe._dict(doctype="Sales Invoice", reference_name="INV-001")

        with patch.object(api, "generate_request_id", return_value="IC-test"):
            api.setup(doc=doc)

        self.assertEqual(
            api.default_log_values["reference_doctype"], "Sales Invoice"
        )
        self.assertEqual(api.default_log_values["reference_name"], "INV-001")

    def test_is_ignored_error_returns_true_for_FO8000_and_updates_response(self):
        api = PublicAPI.__new__(PublicAPI)
        api.gstin = "test-gstin"
        response = frappe._dict(errorCode="FO8000")

        result = api.is_ignored_error(response)

        self.assertTrue(result)
        self.assertEqual(response.sts, "Invalid")
        self.assertEqual(response.gstin, "test-gstin")
        self.assertEqual(response.error_code, "FO8000")

    def test_is_ignored_error_returns_true_for_RET13510(self):
        api = PublicAPI.__new__(PublicAPI)
        api.gstin = "test-gstin"
        response = frappe._dict(errorCode="RET13510")

        result = api.is_ignored_error(response)

        self.assertTrue(result)
        self.assertEqual(response.error_code, "RET13510")

    def test_is_ignored_error_returns_false_for_unknown_code(self):
        api = PublicAPI.__new__(PublicAPI)
        response = frappe._dict(errorCode="UNKNOWN")

        result = api.is_ignored_error(response)

        self.assertFalse(result)

    def test_is_ignored_error_returns_false_for_empty_error_code(self):
        api = PublicAPI.__new__(PublicAPI)
        response = frappe._dict(errorCode="")

        result = api.is_ignored_error(response)

        self.assertFalse(result)

    def test_is_ignored_error_strips_whitespace_from_code(self):
        api = PublicAPI.__new__(PublicAPI)
        response = frappe._dict(errorCode="  FO8000  ")

        result = api.is_ignored_error(response)

        self.assertTrue(result)
