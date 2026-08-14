from unittest.mock import patch

import frappe
import requests
import responses
from frappe.tests import IntegrationTestCase

from india_compliance.exceptions import GatewayTimeoutError, GSPServerError
from india_compliance.gst_india.api_classes.base import (
    BASE_URL,
    SERVER_DOWN_CACHE_KEY,
    BaseAPI,
    get_server_down_key,
    is_server_down,
)

TEST_URL = f"{BASE_URL}/test/ping"


class FailFastAPI(BaseAPI):
    API_NAME = "Test e-Invoice"
    BASE_PATH = "test"
    REQUEST_TIMEOUT = (10, 30)
    FAIL_FAST_IF_SERVER_DOWN = True


class OtherPortalAPI(FailFastAPI):
    API_NAME = "Test e-Waybill"


class DownloadAPI(BaseAPI):
    API_NAME = "Test Download"
    BASE_PATH = "test"


class TestRequestTimeout(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        frappe.cache.delete_keys(SERVER_DOWN_CACHE_KEY)

    def tearDown(self):
        frappe.cache.delete_keys(SERVER_DOWN_CACHE_KEY)
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

    def set_server_down(self, api_name):
        frappe.cache.set_value(get_server_down_key(api_name), True, expires_in_sec=120)

    def test_timeout_sent_with_request(self):
        api = self.create_api()

        with self.mock_request(requests.exceptions.Timeout("timed out")) as mocked:
            self.assertRaises(GatewayTimeoutError, api.get, "ping")

        self.assertEqual(mocked.call_args.kwargs.get("timeout"), (10, 30))

    def test_no_read_timeout_for_downloads(self):
        api = self.create_api(DownloadAPI)

        with self.mock_request(requests.exceptions.Timeout("timed out")) as mocked:
            self.assertRaises(GatewayTimeoutError, api.get, "ping")

        self.assertEqual(mocked.call_args.kwargs.get("timeout"), (10, None))

    def test_timeout_marks_server_down(self):
        api = self.create_api()

        with self.mock_request(requests.exceptions.Timeout("timed out")):
            self.assertRaises(GatewayTimeoutError, api.get, "ping")

        self.assertTrue(is_server_down(FailFastAPI.API_NAME))
        # other portal is untouched
        self.assertFalse(is_server_down(OtherPortalAPI.API_NAME))

    def test_connect_timeout_marks_server_down(self):
        # connect timeout is both a timeout and a connection error
        api = self.create_api()

        with self.mock_request(requests.exceptions.ConnectTimeout("connect timed out")):
            self.assertRaises(GatewayTimeoutError, api.get, "ping")

        self.assertTrue(is_server_down(FailFastAPI.API_NAME))

    def test_connection_error_does_not_mark_server_down(self):
        api = self.create_api()

        with self.mock_request(requests.exceptions.ConnectionError("connection reset")):
            self.assertRaises(GSPServerError, api.get, "ping")

        self.assertFalse(is_server_down(FailFastAPI.API_NAME))

    def test_request_skipped_if_server_is_down(self):
        self.set_server_down(FailFastAPI.API_NAME)
        api = self.create_api()

        with self.mock_request(requests.exceptions.Timeout("timed out")) as mocked:
            self.assertRaises(GSPServerError, api.get, "ping")

        mocked.assert_not_called()

    @responses.activate
    def test_request_made_by_other_portal(self):
        self.set_server_down(FailFastAPI.API_NAME)
        responses.add(responses.GET, TEST_URL, json={"success": True, "result": "pong"}, status=200)

        self.assertEqual(self.create_api(OtherPortalAPI).get("ping"), "pong")

    @responses.activate
    def test_request_made_by_apis_that_dont_fail_fast(self):
        self.set_server_down(DownloadAPI.API_NAME)
        responses.add(responses.GET, TEST_URL, json={"success": True, "result": "pong"}, status=200)

        self.assertEqual(self.create_api(DownloadAPI).get("ping"), "pong")

    @responses.activate
    def test_gateway_timeout_response_marks_server_down(self):
        responses.add(responses.GET, TEST_URL, json={}, status=504)

        self.assertRaises(GatewayTimeoutError, self.create_api().get, "ping")
        self.assertTrue(is_server_down(FailFastAPI.API_NAME))

    @responses.activate
    def test_server_down_response_does_not_mark_server_down(self):
        responses.add(
            responses.GET,
            TEST_URL,
            json={"success": False, "message": "GSPGSTDOWN : GST server is down"},
            status=200,
        )

        self.assertRaises(GSPServerError, self.create_api().get, "ping")
        self.assertFalse(is_server_down(FailFastAPI.API_NAME))
