import base64

from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.serialization import load_pem_public_key

import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime

from india_compliance.gst_india.api_classes.taxpayer_base import StaticResourcesAPI
from india_compliance.gst_india.utils.cryptography import (
    aes_decrypt_data,
    aes_encrypt_data,
    hmac_sha256,
)


def encrypt_using_public_key(data: str, public_key: bytes) -> str:
    public_key = load_pem_public_key(public_key)

    encrypted_msg = public_key.encrypt(plaintext=data, padding=asym_padding.PKCS1v15())
    encoded_encrypted_msg = base64.b64encode(encrypted_msg).decode()

    return encoded_encrypted_msg


class Auth:
    """Base authentication strategy"""

    def __init__(self, client=None):
        self.client = client

    def authenticate(self):
        if self._is_authenticated():
            return

        if not self.client:
            raise ValueError("Client is required for authentication")

        if getattr(self.client, "authenticate", None):
            self.client.authenticate()

    def prepare_request(self, request_args):
        pass

    def process_response(self, response):
        return response

    def _is_authenticated(self):
        return True


class StandardAuth(Auth):
    """NIC authentication with encryption"""

    def prepare_request(self, request_args):
        self._encrypt_request(request_args)

        if self._is_authentication_api(request_args.get("url")):
            return

        request_args["headers"][self.client.AUTH_TOKEN_KEY] = self.client.auth_token

    def process_response(self, response):
        self._decrypt_response(response)
        return response

    def _is_authentication_api(self, url):
        return url.endswith("auth")

    def _is_authenticated(self):
        required_attributes = ("auth_token", "session_key", "session_expiry")

        for attr in required_attributes:
            if not getattr(self.client, attr, None):
                return False

        return self.client.session_expiry >= now_datetime()

    def _encrypt_request(self, request_args):
        """Encrypt request data using public key or session key based on content"""
        json_data = request_args.get("json")
        if not json_data:
            return

        # auth requests => use public key
        if self._is_authentication_api(request_args.get("url")):
            serialized_data = frappe.as_json(json_data)
            encoded_data = base64.b64encode(serialized_data.encode())
            encrypted_data = encrypt_using_public_key(
                encoded_data, self._get_public_key()
            )

        else:
            # other requests => use session key
            encrypted_data = aes_encrypt_data(
                frappe.as_json(json_data), self.client.session_key
            )

        # update request
        params = request_args.pop("params", {}) or {}
        request_args["json"] = {
            "Data": encrypted_data,
            **params,
        }

    def _decrypt_response(self, response):
        """Route response to appropriate decryption method based on content"""
        # get response data
        response_data = response.get(self.client.DATA_KEY) or response
        if not response_data:
            return

        # auth API responses contain auth token
        is_auth_response = (
            isinstance(response_data, dict)
            and self.client.AUTH_TOKEN_KEY in response_data
        )

        if is_auth_response:
            self._decrypt_session_key(response_data)
        else:
            self._decrypt_response_data(response)

    def _decrypt_session_key(self, response):
        """Decrypt and store authentication tokens from auth API response"""
        values = {}

        # extract and store auth token
        auth_token = response.get(self.client.AUTH_TOKEN_KEY)
        if auth_token:
            self.client.auth_token = auth_token
            values["auth_token"] = auth_token

        # decrypt and store session key
        sek_data = response.get(self.client.SEK_KEY)
        if sek_data:
            app_key = base64.b64decode(self.client.app_key.encode())

            # Error raised when incorrect app_key is used: Padding is incorrect
            self.client.session_key = aes_decrypt_data(sek_data, app_key)
            self.client.session_expiry = add_to_date(now_datetime(), hours=6)

            values["session_key"] = base64.b64encode(self.client.session_key).decode()
            values["session_expiry"] = self.client.session_expiry

        # update credentials
        if values:
            credential_filters = {
                "gstin": self.client.company_gstin,
                "username": self.client.username,
                "service": "e-Waybill / e-Invoice",
            }
            frappe.db.set_value("GST Credential", credential_filters, values)
            frappe.clear_document_cache("GST Settings")

    def _decrypt_response_data(self, response):
        """Decrypt response data from non-auth APIs and validate HMAC"""
        # decrypt REK if present
        rek_data = response.get(self.client.REK_KEY)
        decrypted_rek = (
            aes_decrypt_data(rek_data, self.client.session_key) if rek_data else None
        )

        # decrypt main response data
        response_data = response.get(self.client.DATA_KEY)
        if response_data and isinstance(response_data, str):
            decryption_key = decrypted_rek or self.client.session_key
            decrypted_data = aes_decrypt_data(
                response.pop(self.client.DATA_KEY), decryption_key
            )

            # validate HMAC if present
            expected_hmac = response.get(self.client.HMAC_KEY)
            if expected_hmac:
                computed_hmac = hmac_sha256(
                    base64.b64encode(decrypted_data), decrypted_rek
                )
                if computed_hmac != expected_hmac:
                    frappe.throw(_("HMAC mismatch"))

            if result := frappe.parse_json(decrypted_data.decode()):
                response.result = result

    def _get_public_key(self):
        key = self.client.settings.nic_public_key
        if not key:
            key = StaticResourcesAPI().get_nic_public_key()

        return key.encode()


class EnrichedAuth(Auth):
    """Encryption and decryption handled by GSP"""
