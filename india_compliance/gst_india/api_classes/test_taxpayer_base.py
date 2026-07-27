from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from india_compliance.exceptions import InvalidOTPError, OTPRequestedError
from india_compliance.gst_india.api_classes.taxpayer_base import (
    FilesAPI,
    StaticResourcesAPI,
    TaxpayerAuthenticate,
    TaxpayerBaseAPI,
)


class TestTaxpayerAuthenticate(IntegrationTestCase):
    # ---------- decrypt_response ----------

    def test_decrypt_response_stores_auth_token(self):
        auth = TaxpayerAuthenticate.__new__(TaxpayerAuthenticate)
        auth.company_gstin = "27AAAAA0000A1Z5"
        auth.username = "test_user"
        response = frappe._dict({"auth_token": "token123", "expiry": "30"})

        with patch.object(frappe.db, "set_value") as mock_set:
            with patch("frappe.clear_document_cache"):
                result = auth.decrypt_response(response)

        self.assertEqual(auth.auth_token, "token123")
        self.assertIsNotNone(auth.session_expiry)
        mock_set.assert_called_once()
        self.assertEqual(result, response)

    def test_decrypt_response_stores_session_key(self):
        auth = TaxpayerAuthenticate.__new__(TaxpayerAuthenticate)
        auth.company_gstin = "27AAAAA0000A1Z5"
        auth.username = "test_user"
        auth.app_key = "A" * 32
        response = frappe._dict({"sek": "encrypted_sek_value"})

        with patch(
            "india_compliance.gst_india.api_classes.taxpayer_base.aes_decrypt_data",
            return_value=b"decrypted_session_key",
        ):
            with patch.object(frappe.db, "set_value") as mock_set:
                with patch("frappe.clear_document_cache"):
                    result = auth.decrypt_response(response)

        self.assertEqual(auth.session_key, b"decrypted_session_key")
        mock_set.assert_called_once()
        self.assertEqual(result, response)

    # ---------- encrypt_request ----------

    def test_encrypt_request_with_app_key_encrypts_using_public_key(self):
        auth = TaxpayerAuthenticate.__new__(TaxpayerAuthenticate)
        auth.app_key = "test_app_key"
        auth.session_key = b"session_key_16_"
        request_json = {"app_key": "test_app_key", "action": "AUTHTOKEN"}

        with patch(
            "india_compliance.gst_india.api_classes.taxpayer_base.encrypt_using_public_key",
            return_value="encrypted_app_key",
        ):
            with patch.object(auth, "get_public_certificate", return_value=b"cert"):
                auth.encrypt_request(request_json)

        self.assertEqual(request_json["app_key"], "encrypted_app_key")

    def test_encrypt_request_refreshtoken_uses_aes(self):
        auth = TaxpayerAuthenticate.__new__(TaxpayerAuthenticate)
        auth.app_key = "test_app_key"
        auth.session_key = b"session_key_16_"
        request_json = {"app_key": "test_app_key", "action": "REFRESHTOKEN"}

        with patch(
            "india_compliance.gst_india.api_classes.taxpayer_base.aes_encrypt_data",
            return_value="aes_encrypted_key",
        ):
            auth.encrypt_request(request_json)

        self.assertEqual(request_json["app_key"], "aes_encrypted_key")

    # ---------- get_auth_token ----------

    def test_get_auth_token_returns_none_when_no_token(self):
        auth = TaxpayerAuthenticate.__new__(TaxpayerAuthenticate)
        auth.auth_token = None
        auth.session_expiry = None
        self.assertIsNone(auth.get_auth_token())

    def test_get_auth_token_returns_none_when_no_expiry(self):
        auth = TaxpayerAuthenticate.__new__(TaxpayerAuthenticate)
        auth.auth_token = "token123"
        auth.session_expiry = None
        self.assertIsNone(auth.get_auth_token())

    def test_get_auth_token_returns_none_when_expired(self):
        auth = TaxpayerAuthenticate.__new__(TaxpayerAuthenticate)
        auth.auth_token = "token123"
        auth.session_expiry = frappe.utils.add_to_date(None, minutes=-10, as_datetime=True)

        with patch("frappe.utils.now_datetime", return_value=frappe.utils.now_datetime()):
            self.assertIsNone(auth.get_auth_token())

    # ---------- get_public_certificate ----------

    def test_get_public_certificate_from_settings(self):
        auth = TaxpayerAuthenticate.__new__(TaxpayerAuthenticate)
        auth.settings = frappe._dict({"gstn_public_certificate": "existing_cert_pem"})

        with patch(
            "india_compliance.gst_india.api_classes.taxpayer_base.x509.load_pem_x509_certificate"
        ) as mock_load:
            mock_cert = mock_load.return_value
            mock_cert.not_valid_after = frappe.utils.add_to_date(None, days=30, as_datetime=True)

            result = auth.get_public_certificate()

        self.assertEqual(result, b"existing_cert_pem")

    # ---------- get_fy ----------

    def test_get_fy_early_year(self):
        with patch("frappe.utils.getdate") as mock_getdate:
            mock_getdate.return_value.month = 2
            mock_getdate.return_value.year = 2026
            fy = TaxpayerAuthenticate.get_fy()
        self.assertEqual(fy, "2025-26")

    def test_get_fy_later_year(self):
        with patch("frappe.utils.getdate") as mock_getdate:
            mock_getdate.return_value.month = 7
            mock_getdate.return_value.year = 2026
            fy = TaxpayerAuthenticate.get_fy()
        self.assertEqual(fy, "2026-27")


class TestTaxpayerBaseAPI(IntegrationTestCase):
    # ---------- is_ignored_error ----------

    def test_is_ignored_error_returns_true_for_known_codes(self):
        api = TaxpayerBaseAPI.__new__(TaxpayerBaseAPI)
        api.company_gstin = "27AAAAA0000A1Z5"
        response = frappe._dict({"error": {"error_cd": "AUTH158"}})
        self.assertTrue(api.is_ignored_error(response))
        self.assertEqual(response.error_type, "authorization_failed")

    def test_is_ignored_error_returns_true_for_retotprequest(self):
        api = TaxpayerBaseAPI.__new__(TaxpayerBaseAPI)
        api.company_gstin = "27AAAAA0000A1Z5"
        response = frappe._dict({"error": {"error_cd": "RETOTPREQUEST"}})

        with self.assertRaises(OTPRequestedError):
            api.is_ignored_error(response)

    def test_is_ignored_error_raises_for_invalid_otp(self):
        api = TaxpayerBaseAPI.__new__(TaxpayerBaseAPI)
        api.company_gstin = "27AAAAA0000A1Z5"
        response = frappe._dict({"error": {"error_cd": "AUTH4033"}})

        with self.assertRaises(InvalidOTPError):
            api.is_ignored_error(response)

    def test_is_ignored_error_returns_false_for_unknown(self):
        api = TaxpayerBaseAPI.__new__(TaxpayerBaseAPI)
        api.company_gstin = "27AAAAA0000A1Z5"
        response = frappe._dict({"error": {"error_cd": "UNKNOWN_CODE"}})
        self.assertFalse(api.is_ignored_error(response))

    # ---------- get_fy ----------

    def test_get_fy_static_method(self):
        with patch("frappe.utils.getdate") as mock_getdate:
            mock_getdate.return_value.month = 7
            mock_getdate.return_value.year = 2026
            fy = TaxpayerBaseAPI.get_fy()
        self.assertEqual(fy, "2026-27")


class TestStaticResourcesAPI(IntegrationTestCase):
    # ---------- get_gstn_public_certificate ----------

    def test_get_gstn_public_certificate_throws_when_unchanged(self):
        api = StaticResourcesAPI.__new__(StaticResourcesAPI)
        api.settings = frappe._dict({"gstn_public_certificate": "existing_cert"})
        response = frappe._dict({"message": "existing_cert"})

        with patch.object(api, "get", return_value=response):
            with self.assertRaises(frappe.ValidationError):
                api.get_gstn_public_certificate()

    # ---------- get_nic_public_key ----------

    def test_get_nic_public_key_throws_when_unchanged(self):
        api = StaticResourcesAPI.__new__(StaticResourcesAPI)
        api.settings = frappe._dict({"nic_public_key": "existing_key"})
        response = frappe._dict({"message": "existing_key"})

        with patch.object(api, "get", return_value=response):
            with self.assertRaises(frappe.ValidationError):
                api.get_nic_public_key()


class TestFilesAPI(IntegrationTestCase):
    # ---------- process_response ----------
    def test_process_response_raises_on_hash_mismatch(self):
        api = FilesAPI.__new__(FilesAPI)
        api.hash = "expected_hash"
        api.ul = "test_url"

        with patch(
            "india_compliance.gst_india.api_classes.taxpayer_base.hash_sha256",
            return_value="different_hash",
        ):
            with self.assertRaises(frappe.ValidationError):
                api.process_response(b"test_data")
