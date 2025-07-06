import base64
from datetime import datetime

from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.serialization import load_pem_public_key

import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime

from india_compliance.gst_india.api_classes.taxpayer_base import StaticResourcesAPI
from india_compliance.gst_india.utils.cryptography import (
    aes_decrypt_data,
    aes_encrypt_data,
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

        if not self._is_authenticated():
            self.authenticate()

    def authenticate(self):
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

        request_args["headers"][self.client.AUTH_TOKEN] = self.auth_token

    def process_response(self, response):
        self.client.handle_error_response(response)
        self._decrypt_response(response)
        return response

    def _is_authentication_api(self, url):
        return url.endswith("auth")

    def _is_authenticated(self):
        required_attributes = ("auth_token", "session_key", "session_expiry")

        for attr in required_attributes:
            if not getattr(self.client, attr, None):
                return False

        return self.client.session_expiry >= datetime.now()

    def _encrypt_request(self, request_args):
        if not (data := request_args.get("json")):
            return

        key = self.client.USER_NAME
        if key in data:
            data = frappe.as_json(data)
            data = base64.b64encode(data.encode())

            encrypted_data = encrypt_using_public_key(data, self._get_public_key())

        else:
            encrypted_data = aes_encrypt_data(frappe.as_json(data), self.session_key)

        request_args["json"] = {
            "Data": encrypted_data,
            **request_args.pop("params", {}),
        }

    def _decrypt_response(self, response):
        key = self.client.DATA
        data = response.get(key) or response
        if not data:
            return

        key = self.client.AUTH_TOKEN

        if isinstance(data, dict) and key in data:
            self._decrypt_session_key(data)

        else:
            self._decrypt_response_data(response)

    def _decrypt_session_key(self, response):
        # For Auth API
        values = {}
        key = self.client.AUTH_TOKEN
        if response.get(key):
            self.auth_token = response[key]
            values["auth_token"] = response[key]

        key = self.client.SEK
        if response.get(key):
            self.session_key = aes_decrypt_data(
                response[key], base64.b64decode(self.client.app_key.encode())
            )
            self.session_expiry = add_to_date(now_datetime(), hours=6)

            values["session_key"] = base64.b64encode(self.session_key).decode()
            values["session_expiry"] = self.session_expiry

        if values:
            frappe.db.set_value(
                "GST Credential",
                {
                    "gstin": self.client.company_gstin,
                    "username": self.client.username,
                    "service": "e-Waybill / e-Invoice",
                },
                values,
            )

            # cache of parent doctype GST Settings is not cleared by default so clear it manually
            frappe.clear_document_cache("GST Settings")

    def _decrypt_response_data(self, response):
        # For Other APIs
        decrypted_rek = None

        key = self.client.REK
        if response.get(key):
            decrypted_rek = aes_decrypt_data(response[key], self.session_key)

        key = self.client.DATA
        if response.get(key) and isinstance(response[key], str):
            decrypted_data = aes_decrypt_data(
                response.pop(key), decrypted_rek or self.session_key
            )

            if response.get(self.client.HMAC):
                hmac = aes_decrypt_data(base64.b64encode(decrypted_data), decrypted_rek)

                if hmac != response[self.client.HMAC]:
                    frappe.throw(_("HMAC mismatch"))

            response.result = frappe.parse_json(decrypted_data.decode())

    def _get_public_key(self):
        key = self.client.settings.nic_public_key
        if not key:
            key = StaticResourcesAPI().get_nic_public_key()

        return key.encode()


class EnrichedAuth(Auth):
    """Encryption and decryption handled by GSP"""
