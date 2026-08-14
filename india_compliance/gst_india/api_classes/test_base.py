from unittest.mock import patch

import frappe
import requests
import responses
from frappe.tests import IntegrationTestCase

from india_compliance.exceptions import (
    GatewayTimeoutError,
    GSPLimitExceededError,
    GSPServerError,
)
from india_compliance.gst_india.api_classes.base import (
    BASE_URL,
    SERVER_DOWN_CACHE_KEY,
    BaseAPI,
)

TEST_URL = f"{BASE_URL}/test/ping"


class FailFastAPI(BaseAPI):
    API_NAME = "Test Fail Fast"
    BASE_PATH = "test"
    REQUEST_TIMEOUT = (10, 30)
    FAIL_FAST_IF_SERVER_DOWN = True


class SlowAPI(BaseAPI):
    API_NAME = "Test Slow"
    BASE_PATH = "test"


class TestRequestTimeout(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        frappe.cache.delete_value(SERVER_DOWN_CACHE_KEY)

    def tearDown(self):
        frappe.cache.delete_value(SERVER_DOWN_CACHE_KEY)
        super().tearDown()

    def create_api(self, api_class=FailFastAPI):
        """Skip credential setup, only the request cycle is under test."""
        with patch(
            "india_compliance.gst_india.api_classes.base.BaseAPI.__init__",
            return_value=None,
        ):
            api = api_class()

        api.settings = frappe.get_cached_doc("GST Settings")
        api.company_gstin = None
        api.auth_strategy = None
        api.sandbox_mode = False
        api.default_headers = {"x-api-key": "test_api_secret"}
        api.default_log_values = {}
        api.support_email = None

        return api

    def mock_request(self, side_effect):
        return patch(
            "india_compliance.gst_india.api_classes.base.requests.request",
            side_effect=side_effect,
        )

    def test_timeout_sent_with_request(self):
        api = self.create_api()

        with self.mock_request(requests.exceptions.Timeout("timed out")) as mocked:
            self.assertRaises(GatewayTimeoutError, api.get, "ping")

        self.assertEqual(mocked.call_args.kwargs.get("timeout"), (10, 30))

    def test_no_read_timeout_for_downloads(self):
        api = self.create_api(SlowAPI)

        with self.mock_request(requests.exceptions.Timeout("timed out")) as mocked:
            self.assertRaises(GatewayTimeoutError, api.get, "ping")

        self.assertEqual(mocked.call_args.kwargs.get("timeout"), (10, None))

    def test_timeout_marks_server_down(self):
        api = self.create_api()

        with self.mock_request(requests.exceptions.Timeout("timed out")):
            self.assertRaises(GatewayTimeoutError, api.get, "ping")

        self.assertTrue(frappe.cache.get_value(SERVER_DOWN_CACHE_KEY))

    def test_connection_error_marks_server_down(self):
        api = self.create_api()

        with self.mock_request(requests.exceptions.ConnectionError("connection reset")):
            self.assertRaises(GSPServerError, api.get, "ping")

        self.assertTrue(frappe.cache.get_value(SERVER_DOWN_CACHE_KEY))

    def test_request_skipped_if_server_is_down(self):
        frappe.cache.set_value(SERVER_DOWN_CACHE_KEY, True, expires_in_sec=120)
        api = self.create_api()

        with self.mock_request(requests.exceptions.Timeout("timed out")) as mocked:
            self.assertRaises(GSPServerError, api.get, "ping")

        mocked.assert_not_called()

    @responses.activate
    def test_request_made_by_other_apis_if_server_is_down(self):
        frappe.cache.set_value(SERVER_DOWN_CACHE_KEY, True, expires_in_sec=120)
        responses.add(responses.GET, TEST_URL, json={"success": True, "result": "pong"}, status=200)

        self.assertEqual(self.create_api(SlowAPI).get("ping"), "pong")

    @responses.activate
    def test_server_down_response_marks_server_down(self):
        responses.add(
            responses.GET,
            TEST_URL,
            json={"success": False, "message": "GSPGSTDOWN : GST server is down"},
            status=200,
        )

        self.assertRaises(GSPServerError, self.create_api().get, "ping")
        self.assertTrue(frappe.cache.get_value(SERVER_DOWN_CACHE_KEY))

    @responses.activate
    def test_limit_exceeded_does_not_mark_server_down(self):
        responses.add(
            responses.GET,
            TEST_URL,
            json={"success": False, "message": "GEN5005 : limit exceeded"},
            status=200,
        )

        self.assertRaises(GSPLimitExceededError, self.create_api().get, "ping")
        self.assertFalse(frappe.cache.get_value(SERVER_DOWN_CACHE_KEY))
