import base64
import json
from unittest.mock import Mock, patch

import responses
from responses import matchers

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from india_compliance.gst_india.api_classes.base import BASE_URL
from india_compliance.gst_india.api_classes.nic.auth import (
    EnrichedAuth,
    StandardAuth,
    encrypt_using_public_key,
)
from india_compliance.gst_india.api_classes.nic.e_invoice import StandardEInvoiceAPI
from india_compliance.gst_india.api_classes.nic.e_waybill import StandardEWaybillAPI
from india_compliance.gst_india.utils.cryptography import (
    aes_decrypt_data,
    aes_encrypt_data,
)
from india_compliance.gst_india.utils.tests import create_sales_invoice


class TestNICAuth(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.db.set_single_value(
            "GST Settings",
            {
                "enable_api": 1,
                "enable_e_invoice": 1,
                "enable_e_waybill": 1,
                "auto_generate_e_waybill": 0,
                "auto_generate_e_invoice": 0,
                "fetch_e_waybill_data": 0,
                "apply_e_invoice_only_for_selected_companies": 0,
                "sandbox_mode": 0,
            },
        )


class TestStandardAuth(TestNICAuth):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Sample test data structure
        cls.test_data = frappe._dict(
            {
                "public_key": """-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAjo1FvyiKcQ9hDR2+vH0+\nO2XazuLbo2bPfRiiUnpaPhE3ly+Pwh05gvEuzo2UhUIDg98cX4E0vbfWOF1po2wW\nTBxb8jMY1nAJ8fz1xyHc1Wa7KZ0CeTvAGeifkMux7c22pMu6pBGJN8f3q7MnIW/u\nSJloJF6+x4DZcgvnDUlgZD3Pcoi3GJF1THbWQi5pDQ8U9hZsSJfpsuGKnz41QRsK\ns7Dz7qmcKT2WwN3ULWikgCzywfuuREWb4TVE2p3e9WuoDNPUziLZFeUfMP0NqYsi\nGVYHs1tVI25G42AwIVJoIxOWys8Zym9AMaIBV6EMVOtQUBbNIZufix/TwqTlxNPQ\nVwIDAQAB\n-----END PUBLIC KEY-----""",
                "app_key": "OTcyMzIyY2JhYmEyY2Q0MzFkZTdkMGE1MWYxYjczMjY=",
                "session_key": b"test_session_key_32_bytes_long!",
                "auth_token": "1prNqxvNhpW4J6PswjN99F1n8",
                "encrypted_sek": "IRO6LxXkrkb2QqmPT+POIU/LtN3Q3DHpYCr7+/i+KsDZ9FZifEGQD5N9BfnJbt/D",
                "sample_data": {"test": "data", "value": 123},
            }
        )

    def setUp(self):
        super().setUp()
        # Mock client for testing
        self.mock_client = Mock()
        self.mock_client.company_gstin = "24AAUPV7468F1ZW"
        self.mock_client.username = "test_user"
        self.mock_client.password = "test_password"
        self.mock_client.app_key = self.test_data.app_key
        self.mock_client.session_key = self.test_data.session_key
        self.mock_client.auth_token = self.test_data.auth_token
        self.mock_client.session_expiry = add_to_date(now_datetime(), hours=6)

        # Mock API response keys
        self.mock_client.AUTH_TOKEN_KEY = "AuthToken"
        self.mock_client.SEK_KEY = "Sek"
        self.mock_client.REK_KEY = "Rek"
        self.mock_client.DATA_KEY = "Data"
        self.mock_client.HMAC_KEY = "Hmac"

        # Mock settings
        self.mock_client.settings = Mock()
        self.mock_client.settings.nic_public_key = self.test_data.public_key

    def test_encrypt_using_public_key(self):
        """Test public key encryption"""
        test_data = "Hello, World!"
        test_data = base64.b64encode(test_data.encode())
        encrypted = encrypt_using_public_key(
            test_data, self.test_data.public_key.encode()
        )

        # Should return base64 encoded string
        self.assertIsInstance(encrypted, str)

        # Should be valid base64
        try:
            base64.b64decode(encrypted)
        except Exception:
            self.fail("Encrypted data is not valid base64")

    def test_auth_request_encryption_with_public_key(self):
        """Test encryption of auth requests using public key"""
        auth = StandardAuth(self.mock_client)

        request_args = frappe._dict(
            {
                "url": "https://example.com/auth",
                "json": self.test_data.sample_data,
                "headers": {},
            }
        )

        # Mock the public key method
        with patch.object(
            auth, "_get_public_key", return_value=self.test_data.public_key.encode()
        ):
            auth._encrypt_request(request_args)

        # Check that JSON was encrypted
        self.assertIn("Data", request_args.json)
        self.assertIsInstance(request_args.json["Data"], str)

        # Original data should be gone
        self.assertNotIn("test", request_args.json)

    def test_regular_request_encryption_with_session_key(self):
        """Test encryption of regular requests using session key"""
        auth = StandardAuth(self.mock_client)

        request_args = frappe._dict(
            {
                "url": "https://example.com/invoice",
                "json": self.test_data.sample_data,
                "headers": {},
            }
        )

        # Mock AES encryption
        with patch(
            "india_compliance.gst_india.api_classes.nic.auth.aes_encrypt_data"
        ) as mock_encrypt:
            mock_encrypt.return_value = "encrypted_data"
            auth._encrypt_request(request_args)

        # Check encryption was called with correct parameters
        mock_encrypt.assert_called_once_with(
            frappe.as_json(self.test_data.sample_data), self.mock_client.session_key
        )

        # Check that JSON was encrypted
        self.assertIn("Data", request_args.json)
        self.assertEqual(request_args.json["Data"], "encrypted_data")

    def test_auth_response_decryption(self):
        """Test decryption of authentication response"""
        auth = StandardAuth(self.mock_client)

        response = frappe._dict(
            {"AuthToken": "new_auth_token", "Sek": self.test_data.encrypted_sek}
        )

        # Mock AES decryption
        with patch(
            "india_compliance.gst_india.api_classes.nic.auth.aes_decrypt_data"
        ) as mock_decrypt:
            mock_decrypt.return_value = self.test_data.session_key

            # Mock database update
            with patch("frappe.db.set_value") as mock_db_set:
                auth._decrypt_session_key(response)

        # Check that auth token was set
        self.assertEqual(self.mock_client.auth_token, "new_auth_token")

        # Check that session key was set
        self.assertEqual(auth.client.session_key, self.test_data.session_key)

        # Check that database was updated
        mock_db_set.assert_called_once()

    def test_regular_response_decryption(self):
        """Test decryption of regular API responses"""
        auth = StandardAuth(self.mock_client)

        encrypted_data = "encrypted_response_data"
        response = frappe._dict({"Data": encrypted_data})

        decrypted_data = json.dumps({"result": "success"}).encode()

        # Mock AES decryption
        with patch(
            "india_compliance.gst_india.api_classes.nic.auth.aes_decrypt_data"
        ) as mock_decrypt:
            mock_decrypt.return_value = decrypted_data

            auth._decrypt_response_data(response)

        # Check that data was decrypted and parsed
        self.assertEqual(response.result, {"result": "success"})
        self.assertNotIn("Data", response)

    def test_hmac_validation(self):
        """Test HMAC validation in response decryption"""
        auth = StandardAuth(self.mock_client)

        encrypted_data = "encrypted_response_data"
        rek_data = "encrypted_rek"
        decrypted_rek = b"decrypted_rek_key"
        hmac_value = "expected_hmac"

        response = frappe._dict(
            {"Data": encrypted_data, "Rek": rek_data, "Hmac": hmac_value}
        )

        decrypted_data = json.dumps({"result": "success"}).encode()

        # Mock AES decryption and HMAC computation
        with patch(
            "india_compliance.gst_india.api_classes.nic.auth.aes_decrypt_data"
        ) as mock_decrypt:
            mock_decrypt.side_effect = [decrypted_rek, decrypted_data]

            with patch(
                "india_compliance.gst_india.api_classes.nic.auth.hmac_sha256"
            ) as mock_hmac:
                mock_hmac.return_value = hmac_value

                auth._decrypt_response_data(response)

        # Check HMAC was computed correctly
        mock_hmac.assert_called_once_with(
            base64.b64encode(decrypted_data), decrypted_rek
        )

        # Check that data was decrypted successfully
        self.assertEqual(response.result, {"result": "success"})

    def test_hmac_mismatch_error(self):
        """Test HMAC mismatch throws error"""
        auth = StandardAuth(self.mock_client)

        response = frappe._dict(
            {"Data": "encrypted_data", "Rek": "encrypted_rek", "Hmac": "expected_hmac"}
        )

        decrypted_data = json.dumps({"result": "success"}).encode()

        # Mock AES decryption and HMAC computation
        with patch(
            "india_compliance.gst_india.api_classes.nic.auth.aes_decrypt_data"
        ) as mock_decrypt:
            mock_decrypt.side_effect = [b"decrypted_rek", decrypted_data]

            with patch(
                "india_compliance.gst_india.api_classes.nic.auth.hmac_sha256"
            ) as mock_hmac:
                mock_hmac.return_value = "different_hmac"

                with self.assertRaises(frappe.exceptions.ValidationError) as context:
                    auth._decrypt_response_data(response)

                self.assertIn("HMAC mismatch", str(context.exception))

    def test_is_authenticated_check(self):
        """Test authentication status check"""
        auth = StandardAuth(self.mock_client)

        # Should be authenticated with all required attributes
        self.assertTrue(auth._is_authenticated())

        # Should not be authenticated without auth token
        self.mock_client.auth_token = None
        self.assertFalse(auth._is_authenticated())

        # Should not be authenticated without session key
        self.mock_client.auth_token = "token"
        self.mock_client.session_key = None
        self.assertFalse(auth._is_authenticated())

        # Should not be authenticated if session expired
        self.mock_client.session_key = "key"
        self.mock_client.session_expiry = add_to_date(now_datetime(), hours=-1)
        self.assertFalse(auth._is_authenticated())

    def test_encryption_decryption_roundtrip(self):
        """Test that data encrypted and then decrypted remains the same"""
        test_data = {"test": "data", "number": 123, "nested": {"key": "value"}}
        session_key = b"test_session_key_32_bytes_long!!"

        # Encrypt data
        encrypted = aes_encrypt_data(frappe.as_json(test_data), session_key)

        # Decrypt data
        decrypted = aes_decrypt_data(encrypted, session_key)
        decrypted_json = frappe.parse_json(decrypted.decode())

        # Should be identical
        self.assertEqual(test_data, decrypted_json)

    def test_prepare_request_adds_auth_token(self):
        """Test that prepare_request adds auth token to non-auth requests"""
        auth = StandardAuth(self.mock_client)

        request_args = frappe._dict(
            {
                "url": "https://example.com/invoice",
                "headers": {},
                "json": {"test": "data"},
            }
        )

        with patch.object(auth, "_encrypt_request"):
            auth.prepare_request(request_args)

        # Should add auth token
        self.assertEqual(
            request_args.headers[self.mock_client.AUTH_TOKEN_KEY],
            self.mock_client.auth_token,
        )

    def test_prepare_request_skips_auth_token_for_auth_api(self):
        """Test that prepare_request skips auth token for auth API"""
        auth = StandardAuth(self.mock_client)

        request_args = frappe._dict(
            {"url": "https://example.com/auth", "headers": {}, "json": {"test": "data"}}
        )

        with patch.object(auth, "_encrypt_request"):
            auth.prepare_request(request_args)

        # Should not add auth token
        self.assertNotIn(self.mock_client.AUTH_TOKEN_KEY, request_args.headers)

    def test_process_response_calls_decrypt(self):
        """Test that process_response calls decrypt_response"""
        auth = StandardAuth(self.mock_client)

        response = frappe._dict({"test": "response"})

        with patch.object(auth, "_decrypt_response") as mock_decrypt:
            result = auth.process_response(response)

        mock_decrypt.assert_called_once_with(response)
        self.assertEqual(result, response)

    def test_enriched_auth_no_encryption(self):
        """Test that EnrichedAuth doesn't perform encryption/decryption"""
        auth = EnrichedAuth(self.mock_client)

        request_args = frappe._dict(
            {
                "url": "https://example.com/invoice",
                "headers": {},
                "json": {"test": "data"},
            }
        )

        # Should not modify request
        original_json = request_args.json.copy()
        auth.prepare_request(request_args)
        self.assertEqual(request_args.json, original_json)

        # Should not modify response
        response = frappe._dict({"test": "response"})
        original_response = response.copy()
        result = auth.process_response(response)
        self.assertEqual(result, original_response)


class TestEWaybillAuth(TestNICAuth):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Sample test data structure
        cls.test_data = frappe._dict(
            {
                "public_key": """-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAjo1FvyiKcQ9hDR2+vH0+\nO2XazuLbo2bPfRiiUnpaPhE3ly+Pwh05gvEuzo2UhUIDg98cX4E0vbfWOF1po2wW\nTBxb8jMY1nAJ8fz1xyHc1Wa7KZ0CeTvAGeifkMux7c22pMu6pBGJN8f3q7MnIW/u\nSJloJF6+x4DZcgvnDUlgZD3Pcoi3GJF1THbWQi5pDQ8U9hZsSJfpsuGKnz41QRsK\ns7Dz7qmcKT2WwN3ULWikgCzywfuuREWb4TVE2p3e9WuoDNPUziLZFeUfMP0NqYsi\nGVYHs1tVI25G42AwIVJoIxOWys8Zym9AMaIBV6EMVOtQUBbNIZufix/TwqTlxNPQ\nVwIDAQAB\n-----END PUBLIC KEY-----""",
                "app_key": "066735162ae0683016bbdfd800306c12",
                "session_key": "rEF84pU4A7iqkTtZqA8YxrDVvvuEM3K09MxqJuxbCm0=",
            }
        )

    @responses.activate
    def test_ewaybill_with_auth(self):
        """Test complete e-Waybill cycle: auth -> generate -> update -> cancel"""

        # Mock authentication response
        auth_response = {
            "Alert": None,
            "Message": None,
            "alert": None,
            "alert2": None,
            "authtoken": "1prNqxvNhpW4J6PswjN99F1n8",
            "sek": "IRO6LxXkrkb2QqmPT+POIU/LtN3Q3DHpYCr7+/i+KsDZ9FZifEGQD5N9BfnJbt/D",
            "status": 1,
        }

        # Mock e-Waybill generation response
        generate_response = {
            "Alert": None,
            "Message": None,
            "alert": "",
            "alert2": None,
            "data": "+XeIStG3kgCVyzoYt0Tqi2wRGmbJRDG+8h5NC9j1wga1I6PWkWFzjBm5ov3mP8x0vyNkxROTpvkVI2l0H7hYsVxBTmAirKIeqMkUQfPKkctdd99YIBOboaNEHmnjwg9QEs848gqTja/faTs0VTWW99DaLK32o8gmtvcWzy3nUZw=",
            "status": 1,
        }

        # Mock update transporter response
        update_response = {
            "Alert": None,
            "Message": None,
            "alert": "",
            "alert2": None,
            "data": "prpw/6tgj/zOhcni4+0kH7+6T1v27PFa7pTZsZ8LoJhPWNKtk5Dy8mI/yv6zpMHUU/DUX1Uo2CeLFZIC2KSlEUsU7IT0BFwN/T/JbnL24MvkK5GvMl7mHezv5L5nbxLoVgBZJLxJKTtLU89iIYdmUA==",
            "status": 1,
        }

        # Mock cancel response
        cancel_response = {
            "Alert": None,
            "Message": None,
            "alert": None,
            "alert2": None,
            "data": "prpw/6tgj/zOhcni4+0kHw6htQkxPDIKBZ4hjhLnzaojT8NZnjaXE+T/dkQiSFci8Taab02CIFEuomJYYs6sycFATpMlusapu2JbDqUC1n0=",
            "status": 1,
        }

        settings = frappe.get_single("GST Settings")
        settings.credentials = []
        settings.append(
            "credentials",
            {
                "company": "_Test Indian Registered Company",
                "gstin": "24AAQCA8719H1ZC",
                "username": "test_user",
                "password": "test_password",
                "service": "e-Waybill / e-Invoice",
                "app_key": self.test_data.app_key,
            },
        )
        settings.save()

        # Create test sales invoice
        si = create_sales_invoice(
            customer_address="_Test Registered Customer-Billing",
            company_address="_Test Indian Registered Company-Billing",
            is_in_state=True,
            do_not_submit=True,
        )

        # Test the full cycle
        # Initialize e-Waybill API (this will trigger auth)
        self._mock_get_nic_public_key()
        self._mock_ewaybill_auth_response(auth_response)

        api = StandardEWaybillAPI(si)

        # Generate e-Waybill
        generate_data = {
            "supplyType": "O",
            "subSupplyType": 1,
            "docType": "INV",
            "docNo": si.name,
            "docDate": "06/07/2025",
            "fromGstin": "24AAUPV7468F1ZW",
            "toGstin": "24AUTPV8831F1ZZ",
            "itemList": [
                {
                    "itemNo": 1,
                    "productDesc": "Test Item",
                    "hsnCode": "1234",
                    "quantity": 1.0,
                    "qtyUnit": "PCS",
                    "taxableAmount": 100.0,
                    "sgstRate": 9.0,
                    "cgstRate": 9.0,
                    "igstRate": 0.0,
                    "cessRate": 0.0,
                    "cessNonAdvol": 0.0,
                }
            ],
            "transactionType": 1,
            "transMode": 1,
            "transDistance": 29,
            "transporterId": "24AADFT5917A1ZK",
            "vehicleNo": "GJ06AA1113",
            "vehicleType": "R",
        }

        self._mock_ewaybill_generate_response(generate_data, generate_response)

        result = api.generate_e_waybill(generate_data)
        self.assertIsNotNone(result)
        self.assertEqual(result["ewayBillNo"], 621932918803)

        # Update transporter
        update_data = {"ewbNo": "621932918803", "transporterId": "24AADFT5917A1ZK"}

        self._mock_ewaybill_update_response(update_data, update_response)
        update_result = api.update_transporter(update_data)
        self.assertIsNotNone(update_result)
        self.assertEqual(update_result["transporterId"], "24AADFT5917A1ZK")

        # Cancel e-Waybill
        cancel_data = {
            "ewbNo": "621932918803",
            "cancelRsnCode": "3",
            "cancelRmrk": "Trial",
        }

        self._mock_ewaybill_cancel_response(cancel_data, cancel_response)
        cancel_result = api.cancel_e_waybill(cancel_data)
        self.assertIsNotNone(cancel_result)
        self.assertEqual(cancel_result["ewayBillNo"], "621932918803")

    def _mock_get_nic_public_key(self):
        """Mock fetching NIC public key"""
        responses.add(
            responses.GET,
            f"{BASE_URL}/static/nic_public_key",
            json={"message": self.test_data.public_key},
            status=200,
        )

    def _mock_ewaybill_auth_response(self, response_data):
        """Mock e-Waybill authentication response"""
        responses.add(
            responses.POST,
            f"{BASE_URL}/standard/ewb/auth",
            json=response_data,
            status=200,
        )

    def _mock_ewaybill_generate_response(self, request_data, response_data):
        """Mock e-Waybill generation response"""
        session_key = base64.b64decode(self.test_data.session_key)
        json_data = {
            "action": "GENEWAYBILL",
            # Ensure data is encrypted correctly
            "Data": aes_encrypt_data(frappe.as_json(request_data), session_key),
        }

        responses.add(
            responses.POST,
            f"{BASE_URL}/standard/ewb/ewayapi/",
            json=response_data,
            match=[matchers.json_params_matcher(json_data)],
            status=200,
        )

    def _mock_ewaybill_update_response(self, request_data, response_data):
        """Mock e-Waybill update response"""
        session_key = base64.b64decode(self.test_data.session_key)
        json_data = {
            "action": "UPDATETRANSPORTER",
            # Ensure data is encrypted correctly
            "Data": aes_encrypt_data(frappe.as_json(request_data), session_key),
        }

        responses.add(
            responses.POST,
            f"{BASE_URL}/standard/ewb/ewayapi/",
            json=response_data,
            match=[matchers.json_params_matcher(json_data)],
            status=200,
        )

    def _mock_ewaybill_cancel_response(self, request_data, response_data):
        """Mock e-Waybill cancel response"""
        session_key = base64.b64decode(self.test_data.session_key)
        json_data = {
            "action": "CANEWB",
            # Ensure data is encrypted correctly
            "Data": aes_encrypt_data(frappe.as_json(request_data), session_key),
        }

        responses.add(
            responses.POST,
            f"{BASE_URL}/standard/ewb/ewayapi/",
            json=response_data,
            match=[matchers.json_params_matcher(json_data)],
            status=200,
        )


class TestEInvoiceAuth(TestNICAuth):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Sample test data structure
        cls.test_data = frappe._dict(
            {
                "public_key": """-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAjo1FvyiKcQ9hDR2+vH0+\nO2XazuLbo2bPfRiiUnpaPhE3ly+Pwh05gvEuzo2UhUIDg98cX4E0vbfWOF1po2wW\nTBxb8jMY1nAJ8fz1xyHc1Wa7KZ0CeTvAGeifkMux7c22pMu6pBGJN8f3q7MnIW/u\nSJloJF6+x4DZcgvnDUlgZD3Pcoi3GJF1THbWQi5pDQ8U9hZsSJfpsuGKnz41QRsK\ns7Dz7qmcKT2WwN3ULWikgCzywfuuREWb4TVE2p3e9WuoDNPUziLZFeUfMP0NqYsi\nGVYHs1tVI25G42AwIVJoIxOWys8Zym9AMaIBV6EMVOtQUBbNIZufix/TwqTlxNPQ\nVwIDAQAB\n-----END PUBLIC KEY-----""",
                "app_key": "066735162ae0683016bbdfd800306c12",
                "session_key": "9lq1KeAZA8k7n6+haEYVKqW3ON6MSV4fxjUszhoqZkw=",
                "auth_token": "1pfS6VEg8t2QwOtBRQzc5jcjF",
                "encrypted_sek": "90bckfxWIZMIpy9MLFfCJRb1TP8+SgkzQhjIOBgYSXSM9n3fO+MI1lDC9HXXpj6D",
                "sample_data": {"test": "data", "value": 123},
                "irn": "f78753c3cecf4a348addb234636b8897c67565d7f6443ae7a1851a15231f96c8",
            }
        )

    @responses.activate
    def test_full_einvoice_cycle_with_auth(self):
        """Test complete e-Invoice cycle: auth -> generate -> get by IRN -> cancel"""

        # Mock authentication response for e-Invoice
        auth_response = {
            "Data": {
                "AuthToken": self.test_data.auth_token,
                "ClientID": "ADAEQ34GSPXEQUA",
                "Sek": self.test_data.encrypted_sek,
            },
            "Status": 1,
        }

        # Mock e-Invoice generation response
        generate_response = {
            "Data": "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",
            "Status": 1,
        }

        # Mock cancel response
        cancel_response = {
            "Data": "RpOudlXt4EkxjiU0xXmMqtil2a39t2w/ZtTYNUM9skq2zrl4FCBab9iHi0x9FrTMId3BcB4Dr0ycU7QUgt20AEif4P7xoqot61loc4jBybZ0SYN6hEqmNkAWZfKmyChn8A7hCEwVdtYIiyaoD6r42Q==",
            "Status": 1,
        }

        settings = frappe.get_single("GST Settings")
        settings.credentials = []
        settings.append(
            "credentials",
            {
                "company": "_Test Indian Registered Company",
                "gstin": "24AAQCA8719H1ZC",
                "username": "test_user",
                "password": "test_password",
                "service": "e-Waybill / e-Invoice",
                "app_key": self.test_data.app_key,
            },
        )
        settings.save()

        # Create test sales invoice
        si = create_sales_invoice(
            customer_address="_Test Registered Customer-Billing",
            company_address="_Test Indian Registered Company-Billing",
            is_in_state=True,
            do_not_submit=True,
        )

        # Initialize e-Invoice API (this will trigger auth)
        self._mock_get_nic_public_key()
        self._mock_einvoice_auth_response(auth_response)

        api = StandardEInvoiceAPI(si)

        # Generate e-Invoice
        generate_data = {
            "Version": "1.1",
            "TranDtls": {"TaxSch": "GST", "SupTyp": "B2B", "RegRev": "N"},
            "DocDtls": {"Typ": "INV", "No": si.name, "Dt": "06/07/2025"},
            "SellerDtls": {
                "Gstin": "24AAUPV7468F1ZW",
                "LglNm": "Test Company",
                "Addr1": "Test Address",
            },
            "BuyerDtls": {
                "Gstin": "24AUTPV8831F1ZZ",
                "LglNm": "Test Customer",
                "Addr1": "Customer Address",
            },
            "ItemList": [
                {
                    "SlNo": "1",
                    "PrdDesc": "Test Item",
                    "HsnCd": "1234",
                    "Qty": 1.0,
                    "Unit": "PCS",
                    "UnitPrice": 100.0,
                    "TotAmt": 100.0,
                    "AssAmt": 100.0,
                    "GstRt": 18.0,
                    "SgstAmt": 9.0,
                    "CgstAmt": 9.0,
                    "IgstAmt": 0.0,
                    "CesAmt": 0.0,
                    "TotItemVal": 118.0,
                }
            ],
            "ValDtls": {
                "AssVal": 100.0,
                "CgstVal": 9.0,
                "SgstVal": 9.0,
                "IgstVal": 0.0,
                "CesVal": 0.0,
                "TotInvVal": 118.0,
            },
        }

        self._mock_einvoice_generate_response(generate_data, generate_response)
        irn = self.test_data.irn

        result = api.generate_irn(generate_data)
        self.assertIsNotNone(result)
        self.assertEqual(result["Irn"], irn)

        # Cancel e-Invoice
        cancel_data = {"Irn": irn, "CnlRsn": "1", "CnlRem": "Data Entry Mistake"}
        self._mock_einvoice_cancel_response(cancel_data, cancel_response)

        cancel_result = api.cancel_irn(cancel_data)
        self.assertIsNotNone(cancel_result)
        self.assertEqual(cancel_result["Irn"], irn)

    def _mock_get_nic_public_key(self):
        """Mock fetching NIC public key"""
        responses.add(
            responses.GET,
            f"{BASE_URL}/static/nic_public_key",
            json={"message": self.test_data.public_key},
            status=200,
        )

    def _mock_einvoice_auth_response(self, response_data):
        """Mock e-Invoice authentication response"""
        responses.add(
            responses.POST,
            f"{BASE_URL}/standard/ei/api/auth",
            json=response_data,
            status=200,
        )

    def _mock_einvoice_generate_response(self, request_data, response_data):
        """Mock e-Invoice generation response"""
        session_key = base64.b64decode(self.test_data.session_key)
        json_data = {
            # Ensure data is encrypted correctly
            "Data": aes_encrypt_data(frappe.as_json(request_data), session_key),
        }
        responses.add(
            responses.POST,
            f"{BASE_URL}/standard/ei/api/invoice",
            json=response_data,
            match=[matchers.json_params_matcher(json_data)],
            status=200,
        )

    def _mock_einvoice_cancel_response(self, request_data, response_data):
        """Mock e-Invoice cancel response"""
        session_key = base64.b64decode(self.test_data.session_key)
        json_data = {
            # Ensure data is encrypted correctly
            "Data": aes_encrypt_data(frappe.as_json(request_data), session_key),
        }

        responses.add(
            responses.POST,
            f"{BASE_URL}/standard/ei/api/invoice/cancel",
            json=response_data,
            match=[matchers.json_params_matcher(json_data)],
            status=200,
        )
