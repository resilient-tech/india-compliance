import json
from base64 import b64decode, b64encode

from cryptography import x509
from cryptography.hazmat.backends import default_backend

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, now_datetime

from india_compliance.gst_india.api_classes.base import BaseAPI, get_public_ip
from india_compliance.gst_india.utils import merge_dicts, tar_gz_bytes_to_data
from india_compliance.gst_india.utils.cryptography import (
    aes_decrypt_data,
    aes_encrypt_data,
    encrypt_using_public_key,
    hash_sha256,
    hmac_sha256,
)


class PublicCertificate(BaseAPI):
    BASE_PATH = "static"

    def get_gstn_public_certificate(self) -> str:
        response = self.get(endpoint="gstn_g2b_prod_public")
        self.settings.db_set("gstn_public_certificate", response.certificate)

        return response.certificate


class FilesAPI(BaseAPI):
    BASE_PATH = "standard/gstn/files"

    def get_all(self, url_details):
        response = frappe._dict()
        self.encryption_key = b64decode(url_details.ek)

        for row in url_details.urls:
            self.hash = row.get("hash")
            self.ul = row.get("ul")
            data = self.get(endpoint=self.ul)

            if not response:
                response = data
            else:
                merge_dicts(response, data)

        return response

    def process_response(self, response):
        computed_hash = hash_sha256(response)
        if computed_hash != self.hash:
            frappe.throw(
                _(
                    "Hash of file doesn't match for {0}. File may be corrupted or tampered."
                ).format(self.ul)
            )

        encrypted_data = tar_gz_bytes_to_data(response)
        data = self.decrypt_data(encrypted_data)
        data = json.loads(data, object_hook=frappe._dict)

        return data

    def decrypt_data(self, encrypted_json):
        data = aes_decrypt_data(encrypted_json, self.encryption_key)
        return b64decode(data).decode()


class ReturnsAuthenticate(BaseAPI):
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

    def refresh_auth_token(self, auth_token):
        return super().post(
            json={
                "action": "REFRESHTOKEN",
                "app_key": self.app_key,
                "username": self.username,
                "auth_token": auth_token,
            },
            endpoint="authenticate",
        )

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
            json["app_key"] = encrypt_using_public_key(
                self.app_key, self.get_public_certificate()
            )

        if json.get("otp"):
            json["otp"] = aes_encrypt_data(json.get("otp"), self.app_key)

    def get_public_certificate(self):
        certificate = self.settings.gstn_public_certificate

        if not certificate:
            certificate = PublicCertificate().get_gstn_public_certificate()

        cert = x509.load_pem_x509_certificate(certificate.encode(), default_backend())
        valid_up_to = cert.not_valid_after

        if valid_up_to < now_datetime():
            certificate = PublicCertificate().get_gstn_public_certificate()

        return certificate.encode()


class ReturnsAPI(ReturnsAuthenticate):
    API_NAME = "GST Returns"
    BASE_PATH = "standard/gstn"
    SENSITIVE_INFO = BaseAPI.SENSITIVE_INFO + (
        "auth-token",
        "auth_token",
        "app_key",
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
        "RTN_24": "queued",
        "AUTH4033": "invalid_otp",  # Invalid Session
        # "AUTH4034": "invalid_otp",  # Invalid OTP
        "AUTH4038": "authorization_failed",  # Session Expired
        "RET11402": "authorization_failed",  # API Authorization Failed for 2A
        "RET2B1010": "authorization_failed",  # API Authorization Failed for 2B
    }

    def setup(self, company_gstin):
        if self.sandbox_mode:
            frappe.throw(_("Sandbox mode not supported for Returns API"))

        self.company_gstin = company_gstin
        self.fetch_credentials(self.company_gstin, "Returns", require_password=False)
        self.default_headers.update(
            {
                "gstin": self.company_gstin,
                "state-cd": self.company_gstin[:2],
                "username": self.username,
                "ip-usr": frappe.cache.hget("public_ip", "public_ip", get_public_ip),
                "txn": self.generate_request_id(length=32),
            }
        )

    def _fetch_credentials(self, row, require_password=True):
        self.app_key = row.app_key or self.generate_app_key()
        self.auth_token = row.auth_token
        self.session_key = b64decode(row.session_key or "")
        self.session_expiry = row.session_expiry

    def _request(
        self,
        method,
        action,
        return_period=None,
        params=None,
        endpoint=None,
        json=None,
        otp=None,
    ):
        auth_token = self.get_auth_token()

        if not auth_token:
            response = self.autheticate_with_otp(otp=otp)
            if response.error_type in ["otp_requested", "invalid_otp"]:
                return response

        headers = {"auth-token": auth_token}
        if return_period:
            headers["ret_period"] = return_period

        response = getattr(super(), method)(
            params={"action": action, **(params or {})},
            headers=headers,
            json=json,
            endpoint=endpoint,
        )

        if response.error_type == "authorization_failed":
            return self.autheticate_with_otp()

        return response

    def get(self, action, return_period, params=None, endpoint=None, otp=None):
        params = {"gstin": self.company_gstin, **(params or {})}
        return self._request("get", action, return_period, params, endpoint, None, otp)

    def post(self, action, params=None, endpoint=None, json=None, otp=None):
        return self._request("post", action, None, params, endpoint, json, otp)

    def before_request(self, request_args):
        self.encrypt_request(request_args.get("json"))

    def process_response(self, response):
        self.handle_error_response(response)
        response = self.decrypt_response(response)
        return response

    def decrypt_response(self, response):
        decrypted_rek = None

        if response.get("auth_token"):
            return super().decrypt_response(response)

        if response.get("rek"):
            decrypted_rek = aes_decrypt_data(response.rek, self.session_key)

        if response.get("data"):
            decrypted_data = aes_decrypt_data(response.pop("data"), decrypted_rek)

            if response.get("hmac"):
                hmac = hmac_sha256(decrypted_data, decrypted_rek)
                if hmac != response.hmac:
                    frappe.throw(_("HMAC mismatch"))

            response.result = frappe.parse_json(b64decode(decrypted_data).decode())

        return response

    def handle_error_response(self, response):
        success_value = response.get("status_cd") != 0

        if not success_value and not self.is_ignored_error(response):
            frappe.throw(
                response.get("error", {}).get("message")
                # Fallback to response body if message is not present
                or frappe.as_json(response, indent=4),
                title=_("API Request Failed"),
            )

    def is_ignored_error(self, response):
        error_code = response.get("error", {}).get("error_cd")

        if error_code in self.IGNORED_ERROR_CODES:
            response.error_type = self.IGNORED_ERROR_CODES[error_code]
            return True

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

    def get_auth_token(self):
        if not self.auth_token:
            return None

        if not self.session_expiry:
            return None

        if self.session_expiry <= now_datetime():
            return None

        return self.auth_token

    def download_files(self, return_period, token, otp=None):
        response = self.get(
            "FILEDET",
            return_period,
            params={"ret_period": return_period, "token": token},
            endpoint="returns",
            otp=otp,
        )

        if response.error_type == "queued":
            return response

        return FilesAPI().get_all(response)


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
