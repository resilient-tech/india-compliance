from base64 import b64decode, b64encode

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, now_datetime

from india_compliance.gst_india.api_classes.base import BaseAPI
from india_compliance.gst_india.utils.cryptography import (
    aes_decrypt_data,
    aes_encrypt_data,
    encrypt_using_public_key,
    hmac_sha256,
)


class StandardAPI(BaseAPI):
    BASE_PATH = "standard/gstn"
    SENSITIVE_INFO = BaseAPI.SENSITIVE_INFO + (
        "auth-token",
        "app_key",
        "auth_token",
        "sek",
        "rek",
    )

    IGNORED_ERROR_CODES = {
        "RETOTPREQUEST": "otp_requested",
        "EVCREQUEST": "otp_requested",
        "RET11416": "no_docs_found",
        "RET13508": "no_docs_found",
        "RET13509": "no_docs_found",
        "RET13510": "no_docs_found",
        "RET2B1023": "no_docs_found",
        "RET2B1016": "no_docs_found",
        "RT-3BAS1009": "no_docs_found",
        "RET2B1018": "requested_before_cutoff_date",
        "RETINPROGRESS": "queued",
        "AUTH4033": "invalid_otp",  # Invalid Session
        # "AUTH4034": "invalid_otp",  # Invalid OTP
        # "AUTH4038": "authorization_failed",  # Session Expired
        "RET11402": "authorization_failed",  # API Authorization Failed for 2A
        "RET2B1010": "authorization_failed",  # API Authorization Failed for 2B
    }

    def setup(self, company_gstin):
        self.company_gstin = company_gstin
        self.fetch_credentials(self.company_gstin, "Returns", require_password=False)
        self.default_headers.update(
            {
                "gstin": self.company_gstin,
                "state-cd": self.company_gstin[:2],
                "username": self.username,
                "ip-usr": frappe.local.request_ip,
                "txn": self.generate_request_id(length=32),
            }
        )

    def _fetch_credentials(self, row, require_password=True):
        self.app_key = row.app_key or self.generate_app_key()
        self.auth_token = row.auth_token
        self.session_key = b64decode(row.session_key or "")
        self.session_expiry = row.session_expiry

    def is_ignored_error(self, response_json):
        error_code = response_json.get("error").get("error_cd")

        if error_code in self.IGNORED_ERROR_CODES:
            response_json.error_type = self.IGNORED_ERROR_CODES[error_code]
            return True

    def handle_error_response(self, response_json):
        success_value = response_json.get("status_cd") == 1

        if not success_value and not self.is_ignored_error(response_json):
            frappe.throw(
                response_json.get("error").get("message")
                # Fallback to response body if message is not present
                or frappe.as_json(response_json, indent=4),
                title=_("API Request Failed"),
            )

        if response_json.get("data"):
            response_json.data = frappe.parse_json(response_json.data)

    def generate_app_key(self):
        app_key = self.generate_request_id(length=32)
        frappe.db.set_value(
            "GST Credential",
            {
                "gstin": self.company_gstin,
                "username": self.username,
                "service": "Returns",
            },
            {"app_key": app_key},
        )

        return app_key


class Authenticate(StandardAPI):
    def request_otp(self):
        response = super().post(
            json={
                "action": "OTPREQUEST",
                "app_key": self.app_key,
                "username": self.username,
            },
            endpoint="authenticate",
        )

        if response.status_cd != 1:
            return

        return response.update({"error_type": "otp_requested"})

    def autheticate_with_otp(self, otp=None):
        if not otp:
            # reset auth token
            frappe.db.set_value(
                "GST Credential",
                {
                    "gstin": self.company_gstin,
                    "username": self.username,
                    "service": "Returns",
                },
                {"auth_token": None},
            )

            self.auth_token = None
            return self.request_otp()

        return super().post(
            json={
                "action": "AUTHTOKEN",
                "app_key": self.app_key,
                "username": self.username,
                "otp": otp,
            },
            endpoint="authenticate",
        )

    def refresh_token(self, auth_token):
        return super().post(
            json={
                "action": "REFRESHTOKEN",
                "app_key": self.app_key,
                "username": self.username,
                "auth_token": auth_token,
            },
            endpoint="authenticate",
        )

    def fetch_auth_token(self):
        if not self.auth_token:
            return None

        if self.session_expriy <= now_datetime():
            return None

        return self.auth_token

    def decrypt_response(self, response):
        values = {}

        if response.get("auth_token"):
            self.auth_token = response.auth_token
            values["auth_token"] = response.auth_token

        if response.get("expiry"):
            session_expiry = add_to_date(
                None, minutes=cint(response.expiry), as_datetime=True
            )
            self.session_expiry = session_expiry
            values["session_expiry"] = session_expiry

        if response.get("sek"):
            session_key = aes_decrypt_data(response.sek, self.app_key)
            self.session_key = session_key
            values["session_key"] = b64encode(session_key).decode()

        if values:
            frappe.db.set_value(
                "GST Credential",
                {
                    "gstin": self.company_gstin,
                    "username": self.username,
                    "service": "Returns",
                },
                values,
            )

        return response

    def encrypt_request(self, json):
        if not json:
            return

        if json.get("app_key"):
            json["app_key"] = encrypt_using_public_key(self.app_key)

        if json.get("otp"):
            json["otp"] = aes_encrypt_data(json.get("otp"), self.app_key)

        return json


class ReturnsAPI(Authenticate):
    API_NAME = "GST Returns"

    def get(self, action, return_period, params=None, endpoint=None, otp=None):
        auth_token = self.fetch_auth_token()

        if not auth_token:
            response = self.autheticate_with_otp(otp=otp)
            if response.error_type in ["otp_requested", "invalid_otp"]:
                return response

        response = super().get(
            params={"action": action, "gstin": self.company_gstin, **(params or {})},
            headers={
                "gstin": self.company_gstin,
                "ret_period": return_period,
                "auth-token": auth_token,
            },
            endpoint=endpoint,
        )

        if response.error_type == "authorization_failed":
            return self.autheticate_with_otp()

        return response

    def post(
        self, action, return_period, params=None, endpoint=None, json=None, otp=None
    ):
        auth_token = self.fetch_auth_token()

        if not auth_token:
            response = self.autheticate_with_otp(otp=otp)
            if response.error_type in ["otp_requested", "invalid_otp"]:
                return response

        response = super().post(
            params={"action": action, **(params or {})},
            headers={
                "auth-token": auth_token,
            },
            json=json,
            endpoint=endpoint,
        )

        if response.error_type == "authorization_failed":
            return self.autheticate_with_otp()

        return response

    def decrypt_response(self, response):
        if response.get("auth_token"):
            return super().decrypt_response(response)

        if response.get("rek"):
            decrypted_rek = aes_decrypt_data(response.rek, self.session_key)

        if response.get("data"):
            decrypted_data = aes_decrypt_data(response.data, decrypted_rek)
            response.data = b64decode(decrypted_data).decode()

        return response


class GSTR2bAPI(ReturnsAPI):
    API_NAME = "GSTR-2B"

    def get_data(self, return_period, otp=None, file_num=None):
        params = {"rtnprd": return_period}
        if file_num:
            params.update({"file_num": file_num})

        return self.get(
            "GET2B", return_period, params=params, endpoint="returns/gstr2b", otp=otp
        )


class GSTR2aAPI(ReturnsAPI):
    API_NAME = "GSTR-2A"

    def get_data(self, action, return_period, otp=None):
        return self.get(
            action,
            return_period,
            params={"ret_period": return_period},
            endpoint="returns/gstr2a",
            otp=otp,
        )
