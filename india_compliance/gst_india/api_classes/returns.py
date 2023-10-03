from base64 import b64encode

import frappe
from frappe import _
from frappe.utils import add_to_date, now

from india_compliance.gst_india.api_classes.base import BaseAPI
from india_compliance.gst_india.utils.cryptography import (
    aes_decrypt_data,
    aes_encrypt_data,
    encrypt_using_public_key,
    hmac_sha256,
)


class StandardAPI(BaseAPI):
    API_NAME = "GST Standard"
    BASE_PATH = "gstn"
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
        "AUTH4033": "authorization_failed",  # Invalid Session
        "AUTH4034": "otp_requested",  # Invalid OTP
        "AUTH4038": "authorization_failed",  # Session Expired
        "RET11402": "authorization_failed",  # Unauthorized User!
        "RET2B1010": "authorization_failed",
    }

    def setup(self, company_gstin):
        self.company_gstin = company_gstin
        self.fetch_credentials(self.company_gstin, "Returns", require_password=False)
        self.app_key = self.get_app_key()
        self.default_headers.update(
            {
                "state-cd": self.company_gstin[:2],
                "username": self.username,
                "ip-usr": frappe.local.request_ip,
                "txn": self.generate_request_id(length=32),
            }
        )

    def handle_failed_response(self, response_json):
        error_code = response_json.get("error").get("error_cd")

        if error_code in self.IGNORED_ERROR_CODES:
            response_json.error_type = self.IGNORED_ERROR_CODES[error_code]
            return True

    def handle_error_response(self, response_json):
        success_value = response_json.get("status_cd") == 1

        if not success_value and not self.handle_failed_response(response_json):
            frappe.throw(
                response_json.get("error").get("message")
                # Fallback to response body if message is not present
                or frappe.as_json(response_json, indent=4),
                title=_("API Request Failed"),
            )


class Authenticate(StandardAPI):
    API_NAME = "GST Standard Authentication"

    def setup(self, gstin):
        super().setup(gstin)
        self.app_key = self.get_app_key()

    def request_otp(self):
        return self.post(
            {
                "action": "OTPREQUEST",
                "app_key": self.app_key,
                "username": self.username,
            },
            endpoint="authenticate",
        )

    def autheticate(self, otp):
        return self.post(
            {
                "action": "AUTHTOKEN",
                "app_key": self.app_key,
                "username": self.username,
                "otp": otp,
            },
            endpoint="authenticate",
        )

    def refresh_token(self, auth_token):
        return self.post(
            {
                "action": "REFRESHTOKEN",
                "app_key": self.app_key,
                "username": self.username,
                "auth_token": auth_token,
            },
            endpoint="authenticate",
        )

    def fetch_auth_token(self):
        if not self.settings:
            self.settings = frappe.get_cached_doc("GST Settings")

        for row in self.settings.credentials:
            if row.gstin == self.gstin and row.service == "Returns":
                break

        if not row.auth_token or row.auth_token_expiry < now():
            return None

        return row.auth_token

    def decrypt_response(self, response):
        values = {}

        if response.get("auth_token"):
            values["auth_token"] = response.auth_token

        if response.get("auth_token_expiry"):
            values["auth_token_expiry"] = add_to_date(
                now(), seconds=response.get("auth_token_expiry")
            )

        if response.get("sek"):
            self.session_key = aes_decrypt_data(response.sek, self.app_key)
            response.decrypted_sek = self.session_key
            values["session_key"] = str(b64encode(self.session_key))

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
            json["app_key"] = self.encrypt_app_key(json.get("app_key"))

        if json.get("otp"):
            json["otp"] = self.encrypt_otp(json.get("otp"))

        return json

    def encrypt_app_key(self, app_key):
        return encrypt_using_public_key(app_key)

    def encrypt_otp(self, otp):
        session_key = self.get_session_key()
        return aes_encrypt_data(otp, session_key)

    def get_app_key(self):
        app_key = frappe.cache.get_value("gst_app_key")

        if not app_key:
            app_key = self.generate_app_key()

        return app_key

    def generate_app_key(self):
        app_key = self.generate_request_id(length=32)
        frappe.cache.set_value(
            "gst_app_key",
            app_key,
        )
        return app_key

    def validate_auth_token(self):
        auth_token = self.fetch_auth_token()
        if not auth_token:
            response = self.request_otp()
            if response.status_cd != 1:
                return response

        response["error_type"] = "otp_requested"

        return response

    def get_session_key(self):
        pass


class ReturnsAPI(Authenticate, StandardAPI):
    API_NAME = "GST Returns"

    def setup(self, company_gstin):
        super().setup(company_gstin)

    def get(self, action, return_period, params=None, endpoint=None):
        auth_token = self.validate_auth_token

        return super().get(
            params={
                "action": action,
                "gstin": self.company_gstin,
                "ret_period": return_period,
            },
            **(params or {}),
            headers={
                "gstin": self.company_gstin,
                "ret_period": return_period,
                "auth-token": auth_token,
            },
            endpoint=endpoint,
        )

    def post(self, action, return_period, params=None, endpoint=None, json=None):
        auth_token = self.fetch_auth_token()

        return super().post(
            params={
                "action": action,
            },
            **(params or {}),
            headers={
                "auth-token": auth_token,
            },
            json=json,
            endpoint=endpoint,
        )

    def encrypt_request(
        self,
        json,
    ):
        pass

    def decrypt_response(self, response):
        pass

    def valaidate_hmac(self, response):
        pass


class GSTR2bAPI(ReturnsAPI):
    API_NAME = "GSTR-2B"

    def setup(self, company_gstin):
        super().setup(company_gstin)

    def get_data(self, return_period, otp=None, file_num=None):
        if otp:
            response = self.autheticate(otp)
            if response.status_cd != 1:
                return response

        params = {}
        if file_num:
            params = {"file_num": file_num}
        return self.get(
            "GET2B",
            return_period,
            params=params,
            endpoint="returns/gstr2b",
        )


class GSTR2aAPI(ReturnsAPI):
    API_NAME = "GSTR-2A"

    def get_data(
        self,
        action,
        return_period,
        otp=None,
    ):
        if otp:
            response = self.autheticate(otp)
            if response.status_cd != 1:
                return response

        return self.get(
            action,
            return_period,
            endpoint="returns/gstr2a",
        )
