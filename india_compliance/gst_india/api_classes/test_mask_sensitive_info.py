import frappe
from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.api_classes.base import BaseAPI


class TestMaskSensitiveInfo(IntegrationTestCase):
    def test_base_api_mask_sensitive_info_mapping(self):
        """Test that BaseAPI correctly maps sensitive info to appropriate locations"""
        api = BaseAPI()
        mapping = api._get_sensitive_info_mapping()

        self.assertIn("headers", mapping)
        self.assertIn("output", mapping)
        self.assertIn("data", mapping)
        self.assertIn("body", mapping)

        self.assertIn("x-api-key", mapping["headers"])
        self.assertNotIn("x-api-key", mapping["output"])
        self.assertNotIn("x-api-key", mapping["data"])
        self.assertNotIn("x-api-key", mapping["body"])

    def test_mask_sensitive_info_headers_only(self):
        """Test that sensitive headers are masked only in headers"""
        api = BaseAPI()

        log = frappe._dict(
            {
                "request_headers": {
                    "x-api-key": "secret_key",
                    "content-type": "application/json",
                },
                "output": {"x-api-key": "should_not_be_masked", "result": "success"},
                "data": {"x-api-key": "should_not_be_masked", "param": "value"},
                "body": None,
            }
        )

        api.mask_sensitive_info(log)

        self.assertEqual(log.request_headers["x-api-key"], api.PLACEHOLDER)
        self.assertEqual(log.request_headers["content-type"], "application/json")

        self.assertEqual(log.output["x-api-key"], "should_not_be_masked")
        self.assertEqual(log.data["x-api-key"], "should_not_be_masked")

    def test_mask_sensitive_info_with_request_body(self):
        """Test that sensitive info in request body is handled correctly"""
        api = BaseAPI()

        log = frappe._dict(
            {
                "request_headers": {"content-type": "application/json"},
                "output": {"result": "success"},
                "data": {
                    "params": {"test": "value"},
                    "body": {"password": "secret_password", "AppKey": "secret_app_key"},
                },
            }
        )

        api.mask_sensitive_info(log)

        self.assertEqual(log.data["body"]["password"], BaseAPI.PLACEHOLDER)
        self.assertEqual(log.data["body"]["AppKey"], BaseAPI.PLACEHOLDER)
        self.assertEqual(log.data["params"]["test"], "value")

    def test_mask_sensitive_info_comprehensive(self):
        """Test complete masking with all data structures"""
        api = BaseAPI.__new__(BaseAPI)

        log = frappe._dict(
            {
                "request_headers": {
                    "x-api-key": "secret_api_key",
                    "auth-token": "secret_auth_token",
                    "content-type": "application/json",
                },
                "output": {
                    "auth_token": "response_auth_token",
                    "sek": "session_encryption_key",
                    "rek": "response_encryption_key",
                    "result": "success",
                },
                "data": {
                    "app_key": "data_app_key",
                    "body": {"app_key": "body_app_key", "username": "test_user"},
                },
            }
        )

        api.mask_sensitive_info(log)

        self.assertEqual(log.request_headers["x-api-key"], BaseAPI.PLACEHOLDER)
        self.assertEqual(log.request_headers["auth-token"], BaseAPI.PLACEHOLDER)
        self.assertEqual(log.request_headers["content-type"], "application/json")

        self.assertEqual(log.output["auth_token"], BaseAPI.PLACEHOLDER)
        self.assertEqual(log.output["sek"], BaseAPI.PLACEHOLDER)
        self.assertEqual(log.output["rek"], BaseAPI.PLACEHOLDER)
        self.assertEqual(log.output["result"], "success")

        self.assertEqual(log.data["app_key"], BaseAPI.PLACEHOLDER)
        self.assertEqual(log.data["body"]["app_key"], BaseAPI.PLACEHOLDER)
        self.assertEqual(log.data["body"]["username"], "test_user")

    def test_mask_sensitive_info_handles_missing_data(self):
        """Test that masking works when some data structures are missing"""
        api = BaseAPI()

        log = frappe._dict(
            {
                "request_headers": {"x-api-key": "secret_key"},
                "output": None,
                "data": None,
            }
        )

        api.mask_sensitive_info(log)

        self.assertEqual(log.request_headers["x-api-key"], BaseAPI.PLACEHOLDER)

    def test_mask_sensitive_info_no_false_positives(self):
        """Test that legitimate data with similar keys is not masked inappropriately"""
        api = BaseAPI.__new__(BaseAPI)

        log = frappe._dict(
            {
                "request_headers": {"content-type": "application/json"},
                "output": {
                    "password_reset_link": "https://example.com/reset",
                    "result": "success",
                },
                "data": {
                    "user_password_policy": "strong",
                    "body": {"password": "actual_secret"},
                },
            }
        )

        api.mask_sensitive_info(log)

        self.assertEqual(log.output["password_reset_link"], "https://example.com/reset")
        self.assertEqual(log.data["user_password_policy"], "strong")
        self.assertEqual(log.data["body"]["password"], BaseAPI.PLACEHOLDER)

    def test_sensitive_info_overrides_functionality(self):
        """Test that the override system works correctly - only specified locations are overridden"""

        class CustomAPI(BaseAPI):
            def _get_sensitive_info_overrides(self):
                return {
                    "headers": ["custom-header", "x-api-key"],
                }

        api = CustomAPI.__new__(CustomAPI)
        mapping = api._get_sensitive_info_mapping()

        self.assertEqual(mapping["headers"], ["custom-header", "x-api-key"])

        self.assertEqual(mapping["output"], BaseAPI.DEFAULT_MASK_MAP["output"])
        self.assertEqual(mapping["data"], BaseAPI.DEFAULT_MASK_MAP["data"])
        self.assertEqual(mapping["body"], BaseAPI.DEFAULT_MASK_MAP["body"])

    def test_empty_overrides_uses_defaults(self):
        """Test that empty overrides still use default mapping"""

        class NoOverrideAPI(BaseAPI):
            def _get_sensitive_info_overrides(self):
                return {}

        api = NoOverrideAPI.__new__(NoOverrideAPI)
        mapping = api._get_sensitive_info_mapping()

        self.assertEqual(mapping, BaseAPI.DEFAULT_MASK_MAP)
