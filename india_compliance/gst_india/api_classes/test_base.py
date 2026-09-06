import pickle
import time
from unittest.mock import patch

import frappe
import requests
import responses
from frappe.tests import IntegrationTestCase

from india_compliance.exceptions import GatewayTimeoutError, GSPLimitExceededError, GSPServerError
from india_compliance.gst_india.api_classes.base import BASE_URL, BaseAPI
from india_compliance.gst_india.utils import (
    INFLIGHT_STALE_SECONDS,
    clear_portal_slow,
    clear_server_down,
    get_inflight_key,
    get_server_down_key,
    inflight_in_web,
    is_portal_slow,
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
        self.clear_portal_state()

    def tearDown(self):
        self.clear_portal_state()
        super().tearDown()

    def clear_portal_state(self):
        clear_server_down(FailFastAPI.API_NAME, OtherPortalAPI.API_NAME, DownloadAPI.API_NAME)
        clear_portal_slow()
        frappe.cache.unlink(get_inflight_key())

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
        frappe.cache.set_value(get_server_down_key(api_name), True, expires_in_sec=120, shared=True)

    def in_web_request(self, request=None):
        """look like a web request"""
        if request is None:
            request = frappe._dict(method="GET", path="/api/method/ping")

        return patch.object(frappe.local, "request", request, create=True)

    def portal_recording_inflight(self, seen):
        def portal(*args, **kwargs):
            seen.append(inflight_in_web())
            raise requests.exceptions.Timeout("timed out")

        return portal

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

    def test_connection_error_marks_server_down(self):
        api = self.create_api()

        with self.mock_request(requests.exceptions.ConnectionError("connection reset")):
            self.assertRaises(GSPServerError, api.get, "ping")

        self.assertTrue(is_server_down(FailFastAPI.API_NAME))

    def test_request_skipped_if_server_is_down(self):
        self.set_server_down(FailFastAPI.API_NAME)
        api = self.create_api()

        with self.mock_request(requests.exceptions.Timeout("timed out")) as mocked:
            self.assertRaises(GSPServerError, api.get, "ping")

        mocked.assert_not_called()
        # a message of our own to show, and for the caller to clear
        self.assertIn("Government services", str(frappe.message_log[-1]))

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
    def test_server_down_response_marks_server_down(self):
        responses.add(
            responses.GET,
            TEST_URL,
            json={"success": False, "message": "GSPGSTDOWN : GST server is down"},
            status=200,
        )

        self.assertRaises(GSPServerError, self.create_api().get, "ping")
        self.assertTrue(is_server_down(FailFastAPI.API_NAME))

    @responses.activate
    def test_other_errors_do_not_mark_server_down(self):
        responses.add(
            responses.GET,
            TEST_URL,
            json={"success": False, "message": "Invalid GSTIN"},
            status=200,
        )

        self.assertRaises(frappe.ValidationError, self.create_api().get, "ping")
        self.assertFalse(is_server_down(FailFastAPI.API_NAME))

    @responses.activate
    def test_bad_gateway_marks_server_down(self):
        responses.add(responses.GET, TEST_URL, json={}, status=502)

        self.assertRaises(GSPServerError, self.create_api().get, "ping")
        self.assertTrue(is_server_down(FailFastAPI.API_NAME))

    @responses.activate
    def test_service_unavailable_marks_server_down(self):
        responses.add(responses.GET, TEST_URL, json={}, status=503)

        self.assertRaises(GSPServerError, self.create_api().get, "ping")
        self.assertTrue(is_server_down(FailFastAPI.API_NAME))

    @responses.activate
    def test_internal_error_does_not_mark_server_down(self):
        # a 500 can be one bad request, not an outage
        responses.add(responses.GET, TEST_URL, json={}, status=500)

        self.assertRaises(requests.exceptions.HTTPError, self.create_api().get, "ping")
        self.assertFalse(is_server_down(FailFastAPI.API_NAME))

    @responses.activate
    def test_limit_exceeded_does_not_mark_server_down(self):
        # per account, other companies can still generate
        responses.add(
            responses.GET,
            TEST_URL,
            json={"success": False, "message": "GEN5005 : GSP account limit exceeded"},
            status=200,
        )

        self.assertRaises(GSPLimitExceededError, self.create_api().get, "ping")
        self.assertFalse(is_server_down(FailFastAPI.API_NAME))

    def test_sandbox_is_not_an_outage(self):
        api = self.create_api()

        with patch.dict(frappe.flags, {"in_test": False}):
            self.assertTrue(api.is_outage(GatewayTimeoutError()))
            self.assertFalse(api.is_outage(GSPLimitExceededError()))
            self.assertFalse(api.is_outage(frappe.ValidationError()))

            api.sandbox_mode = True
            self.assertFalse(api.is_outage(GatewayTimeoutError()))

        # test site is sandbox, retry tests still need the breaker
        self.assertTrue(api.is_outage(GatewayTimeoutError()))

    def test_is_server_down_is_not_memoized(self):
        """bulk job must see the flag expire mid-run"""
        key = frappe.cache.make_key(get_server_down_key(FailFastAPI.API_NAME), shared=True)

        # change it behind the process cache's back, like another worker would
        frappe.cache.set(key, pickle.dumps(True), ex=120)
        self.assertTrue(is_server_down(FailFastAPI.API_NAME))

        frappe.cache.unlink(key)
        self.assertFalse(is_server_down(FailFastAPI.API_NAME))

    @responses.activate
    def test_slow_response_marks_portal_slow(self):
        responses.add(responses.GET, TEST_URL, json={"success": True, "result": "pong"}, status=200)

        with patch("india_compliance.gst_india.api_classes.base.SLOW_RESPONSE_SECONDS", -1):
            self.assertEqual(self.create_api().get("ping"), "pong")

        # slow reroutes, it doesn't refuse
        self.assertTrue(is_portal_slow())
        self.assertFalse(is_server_down(FailFastAPI.API_NAME))

    @responses.activate
    def test_fast_response_does_not_mark_portal_slow(self):
        responses.add(responses.GET, TEST_URL, json={"success": True, "result": "pong"}, status=200)

        self.assertEqual(self.create_api().get("ping"), "pong")
        self.assertFalse(is_portal_slow())

    @responses.activate
    def test_slow_response_ignored_for_apis_that_dont_fail_fast(self):
        responses.add(responses.GET, TEST_URL, json={"success": True, "result": "pong"}, status=200)

        with patch("india_compliance.gst_india.api_classes.base.SLOW_RESPONSE_SECONDS", -1):
            self.assertEqual(self.create_api(DownloadAPI).get("ping"), "pong")

        self.assertFalse(is_portal_slow())

    @responses.activate
    def test_slow_sandbox_does_not_mark_portal_slow(self):
        # bench-wide flag, don't let sandbox reroute real sites
        api = self.create_api()
        api.sandbox_mode = True  # also prefixes the url with /test
        responses.add(
            responses.GET, api.get_url("ping"), json={"success": True, "result": "pong"}, status=200
        )

        with (
            patch("india_compliance.gst_india.api_classes.base.SLOW_RESPONSE_SECONDS", -1),
            patch.dict(frappe.flags, {"in_test": False}),
        ):
            self.assertEqual(api.get("ping"), "pong")

        self.assertFalse(is_portal_slow())

    def test_inflight_counted_while_holding_a_web_worker(self):
        seen = []

        with self.in_web_request(), self.mock_request(self.portal_recording_inflight(seen)):
            self.assertRaises(GatewayTimeoutError, self.create_api().get, "ping")

        self.assertEqual(seen, [1])
        # released even though the call failed
        self.assertEqual(inflight_in_web(), 0)

    def test_inflight_not_counted_in_a_background_worker(self):
        seen = []

        with self.in_web_request(request=None), self.mock_request(self.portal_recording_inflight(seen)):
            frappe.local.request = None
            self.assertRaises(GatewayTimeoutError, self.create_api().get, "ping")

        self.assertEqual(seen, [0])

    def test_inflight_not_counted_for_apis_that_dont_fail_fast(self):
        seen = []

        with self.in_web_request(), self.mock_request(self.portal_recording_inflight(seen)):
            self.assertRaises(GatewayTimeoutError, self.create_api(DownloadAPI).get, "ping")

        self.assertEqual(seen, [0])

    def test_stale_inflight_entries_are_not_counted(self):
        # killed worker left its entry behind
        frappe.cache.zadd(get_inflight_key(), {"dead-worker": time.time() - INFLIGHT_STALE_SECONDS - 1})
        frappe.cache.zadd(get_inflight_key(), {"live-worker": time.time()})

        self.assertEqual(inflight_in_web(), 1)
