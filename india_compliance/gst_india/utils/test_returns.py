import re

import responses

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, cint

from india_compliance.gst_india.api_classes.base import BASE_URL
from india_compliance.gst_india.api_classes.returns import (
    ReturnsAPI,
    ReturnsAuthenticate,
)
from india_compliance.gst_india.utils.cryptography import encrypt_using_public_key


class TestReturns(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.doc = frappe.get_doc("Purchase Reconciliation Tool")
        cls.doc.company = "_Test Indian Registered Company"
        cls.doc.company_gstin = "24AAQCA8719H1ZC"
        cls.doc.save()

        cls.test_data = frappe._dict(
            frappe.get_file_json(
                frappe.get_app_path(
                    "india_compliance", "gst_india", "data", "test_returns.json"
                )
            )
        )

        cls.settings = update_gst_settings(cls.test_data)

    @responses.activate
    def test_get_public_certificate(self):
        # Test Old certificate

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(Public Certificate has expired)$"),
            encrypt_using_public_key,
            "07d4fd376dd7a64b36ca081e28958cb7",
            self.settings.gstn_public_certificate.encode(),
        )

        # Test generate certificate
        self.settings.db_set("gstn_public_certificate", "")

        public_certificate_data = self.test_data.get("gstn_public_certificate")
        self._mock_api_response(
            method="GET",
            api_endpoint="static/gstn_g2b_prod_public",
            data=public_certificate_data.get("response"),
        )

        certificate_response = public_certificate_data.get("response").get(
            "certificate"
        )

        self.assertEqual(
            ReturnsAuthenticate().get_public_certificate(),
            certificate_response.encode(),
        )

        self.assertEqual(
            frappe.get_cached_value("GST Settings", None, "gstn_public_certificate"),
            certificate_response,
        )

    @responses.activate
    def test_autheticate_with_otp(self):
        api = "standard/gstn/authenticate"
        otp_request_data = self.test_data.get("otp_request")

        self._mock_api_response(
            method="GET", url="https://api.ipify.org", data="202.47.112.9"
        )

        public_certificate_data = self.test_data.get("gstn_public_certificate")
        self._mock_api_response(
            method="GET",
            api_endpoint="static/gstn_g2b_prod_public",
            data=public_certificate_data.get("response"),
        )

        return_api = ReturnsAPI(self.doc.company_gstin)
        # Request OTP
        self._mock_api_response(
            api_endpoint=api,
            data=otp_request_data.get("response"),
        )

        self.assertDictEqual(
            return_api.autheticate_with_otp(),
            otp_request_data.get("response"),
        )

        # Authenticate OTP
        authentication_data = self.test_data.get("authenticate_otp")

        self._mock_api_response(
            api_endpoint=api,
            data=authentication_data.get("response"),
        )

        self.assertEqual(
            return_api.autheticate_with_otp(
                authentication_data.get("request_args").get("otp")
            ),
            authentication_data.get("response"),
        )

    def test_encrypt_request(self):
        encrypt_request_data = self.test_data.get("encrypt_request")
        request_args = frappe._dict(encrypt_request_data.get("request_args")).copy()

        ReturnsAPI(self.doc.company_gstin).encrypt_request(request_args)

        self.assertEqual(
            request_args.get("otp"),
            encrypt_request_data.get("response").get("otp"),
        )

    def test_decrypt_response(self):
        decrypt_response_data = self.test_data.get("decrypt_response")
        response = frappe._dict(decrypt_response_data.get("response"))

        self.assertDictEqual(
            ReturnsAPI(self.doc.company_gstin).decrypt_response(response),
            response,
        )

        gst_credentials = frappe.db.get_value(
            "GST Credential",
            {
                "gstin": self.doc.company_gstin,
                "username": "admin",
                "service": "Returns",
            },
            ["auth_token", "session_expiry"],
            as_dict=1,
        )

        self.assertEqual(
            gst_credentials.auth_token,
            response.get("auth_token"),
        )

        session_expiry = add_to_date(
            None, minutes=cint(response.expiry), as_datetime=True
        )

        self.assertEqual(
            str(gst_credentials.session_expiry)[:-7], str(session_expiry)[:-7]
        )

    def _mock_api_response(
        self, method="POST", api_endpoint=None, url=None, data=None, match_list=None
    ):
        """Mock Return APIs response for given data and match_list"""
        if not url:
            url = f"{BASE_URL}/{api_endpoint}"

        response_method = responses.GET if method == "GET" else responses.POST

        responses.add(
            response_method,
            url,
            json=data,
            match=match_list or [],
            status=200,
        )


def update_gst_settings(test_data):
    settings = frappe.get_doc("GST Settings")
    settings.gstn_public_certificate = test_data.get("old_certificate")
    settings.sandbox_mode = 0

    settings.append(
        "credentials",
        {
            "company": "_Test Indian Registered Company",
            "service": "Returns",
            "gstin": "24AAQCA8719H1ZC",
            "username": "admin",
            "app_key": "07d4fd376dd7a64b36ca081e28958cb7",
        },
    )

    settings.save()
    return settings
