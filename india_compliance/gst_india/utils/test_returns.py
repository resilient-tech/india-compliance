import responses
from responses import matchers

import frappe
from frappe.tests.utils import FrappeTestCase, change_settings

from india_compliance.gst_india.api_classes.base import BASE_URL
from india_compliance.gst_india.api_classes.returns import (
    PublicCertificate,
    ReturnsAuthenticate,
)


class TestReturns(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.test_data = frappe._dict(
            frappe.get_file_json(
                frappe.get_app_path(
                    "india_compliance", "gst_india", "data", "test_returns.json"
                )
            )
        )

    @change_settings("GST Settings", {"gstn_public_certificate": ""})
    @responses.activate
    def test_get_public_certificate(self):
        public_certificate_data = self.test_data.get("gstn_public_certificate")
        self._mock_api_response(
            method="GET",
            api="static/gstn_g2b_prod_public",
            data=public_certificate_data.get("response"),
        )

        certificate_response = public_certificate_data.get("response").get(
            "certificate"
        )

        self.assertEqual(
            PublicCertificate().get_gstn_public_certificate(),
            certificate_response,
        )

        self.assertEqual(
            frappe.get_cached_value("GST Settings", None, "gstn_public_certificate"),
            certificate_response,
        )

    def test_autheticate_with_otp(self):
        api = "standard/gstn/authenticate"
        otp_request_data = self.test_data.get("otp_request")

        # Request OTP
        self._mock_api_response(
            api=api,
            data=otp_request_data.get("response"),
            match_list=[
                matchers.header_matcher(
                    otp_request_data.get("headers"),
                    matchers.json_params_matcher(otp_request_data.get("request_args")),
                )
            ],
        )

        self.assertEqual(
            ReturnsAuthenticate().autheticate_with_otp(),
            otp_request_data.get("response"),
        )

        # Authenticate OTP

    def _mock_api_response(self, method="POST", api=None, data=None, match_list=None):
        """Mock Return APIs response for given data and match_list"""
        url = f"{BASE_URL}/test/{api}"

        response_method = responses.GET if method == "GET" else responses.POST

        responses.add(
            response_method,
            url,
            json=data,
            match=match_list,
            status=200,
        )
