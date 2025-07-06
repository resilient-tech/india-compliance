import json
from base64 import b64decode, b64encode
from functools import wraps

from cryptography import x509
from cryptography.hazmat.backends import default_backend

import frappe
import frappe.utils
from frappe import _
from frappe.utils import add_to_date, cint, now_datetime

from india_compliance.exceptions import (
    InvalidAuthTokenError,
    InvalidOTPError,
    OTPRequestedError,
)
from india_compliance.gst_india.api_classes.base import BaseAPI
from india_compliance.gst_india.utils import merge_dicts, tar_gz_bytes_to_data
from india_compliance.gst_india.utils.cryptography import (
    aes_decrypt_data,
    aes_encrypt_data,
    encrypt_using_public_key,
    hash_sha256,
    hmac_sha256,
)


def otp_handler(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)

        except OTPRequestedError as e:
            return e.response

        except InvalidOTPError as e:
            return e.response

        except Exception as e:
            raise e

    return wrapper


class StaticResourcesAPI(BaseAPI):
    BASE_PATH = "static"

    def get_gstn_public_certificate(self, error_message=None) -> str:
        response = self.get(endpoint="gstn_public_certificate")

        if response.message == self.settings.gstn_public_certificate:
            frappe.throw(error_message or _("Public Certificate is already up to date"))

        self.settings.db_set("gstn_public_certificate", response.message)

        return response.message

    def get_nic_public_key(self, error_message=None) -> str:
        response = self.get(endpoint="nic_public_key")

        if response.message == self.settings.nic_public_key:
            frappe.throw(error_message or _("Public Key is already up to date"))

        self.settings.db_set("nic_public_key", response.message)

        return response.message


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


class TaxpayerAuthenticate(BaseAPI):
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
        "AUTH158": "authorization_failed",  # GSTR1
        "AUTH4033": "invalid_otp",  # Invalid Session
        # "AUTH4034": "invalid_otp",  # Invalid OTP
        "AUTH4038": "authorization_failed",  # Session Expired
        "TEC4002": "invalid_public_key",
        "RET13506": "OTP is either expired or incorrect",
        "RET00003": "Return Form already ready to be filed",  # Actions performed on portal directly
        "RET09001": "Latest Summary is not available. Please generate summary and try again.",  # Actions performed on portal directly
    }

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

        response.update({"error_type": "otp_requested", "gstin": self.company_gstin})

        raise OTPRequestedError(response=response)

    def autheticate_with_otp(self, otp=None):
        if not otp:
            # in enqueue / cron job
            if getattr(frappe.local, "job", None):
                frappe.local.job.after_job.add(self.reset_auth_token)
                raise InvalidAuthTokenError

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

        response = super().post(
            json={
                "action": "AUTHTOKEN",
                "app_key": self.app_key,
                "username": self.username,
                "otp": otp,
            },
            endpoint="authenticate",
        )

        frappe.cache.set_value(
            f"authenticated_gstin:{self.company_gstin}",
            True,
            expires_in_sec=60 * 15,
        )

        return response

    def refresh_auth_token(self):
        auth_token = self.get_auth_token()

        if not auth_token:
            return

        return super().post(
            json={
                "action": "REFRESHTOKEN",
                "app_key": self.app_key,
                "username": self.username,
                "auth_token": auth_token,
            },
            endpoint="authenticate",
        )

    def initiate_otp_for_evc(self, pan, form_type):
        return self.get(
            action="EVCOTP",
            params={"pan": pan, "form_type": form_type},
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

            # cache of parent doctype GST Settings is not cleared by default so clear it manually
            frappe.clear_document_cache("GST Settings")

        return response

    def encrypt_request(self, json):
        if not json:
            return

        if json.get("app_key"):
            json["app_key"] = (
                aes_encrypt_data(self.app_key, self.session_key)
                if json.get("action") == "REFRESHTOKEN"
                else encrypt_using_public_key(
                    self.app_key, self.get_public_certificate()
                )
            )

        if json.get("otp"):
            json["otp"] = aes_encrypt_data(json.get("otp"), self.app_key)

    def get_public_certificate(self):
        certificate = self.settings.gstn_public_certificate

        if not certificate:
            certificate = StaticResourcesAPI().get_gstn_public_certificate()

        cert = x509.load_pem_x509_certificate(certificate.encode(), default_backend())
        valid_up_to = cert.not_valid_after

        if valid_up_to < now_datetime():
            certificate = StaticResourcesAPI().get_gstn_public_certificate()

        return certificate.encode()

    def get_auth_token(self):
        if not self.auth_token:
            return None

        if not self.session_expiry:
            return None

        if self.session_expiry <= now_datetime():
            return None

        return self.auth_token

    def reset_auth_token(self):
        """
        Reset after job to clear the auth token
        """
        frappe.db.set_value(
            "GST Credential",
            {
                "gstin": self.company_gstin,
                "username": self.username,
                "service": "Returns",
            },
            {"auth_token": None},
        )

        if not frappe.flags.in_test:
            frappe.db.commit()  # nosemgrep - executed in after enqueue


class TaxpayerBaseAPI(TaxpayerAuthenticate):
    BASE_PATH = "standard/gstn"

    IGNORED_ERROR_CODES = {
        **TaxpayerAuthenticate.IGNORED_ERROR_CODES,
        "RT-R1R3BAV-1007": "authorization_failed",  # Either auth-token or username is invalid. Raised in get_filing_preference
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
                "txn": self.generate_request_id(length=32),
            }
        )

    def _request(
        self,
        method,
        action=None,
        return_type=None,
        return_period=None,
        params=None,
        endpoint=None,
        json=None,
        otp=None,
    ):
        auth_token = self.get_auth_token()

        if not auth_token or otp:
            response = self.autheticate_with_otp(otp=otp)
            if response.error_type in ["otp_requested", "invalid_otp"]:
                return response

        headers = {"auth-token": auth_token}
        if return_type:
            headers["rtn_typ"] = return_type
            headers["userrole"] = return_type

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

    def get(self, *args, **kwargs):
        params = {"gstin": self.company_gstin, **(kwargs.pop("params", {}))}
        return self._request("get", *args, **kwargs, params=params)

    def post(self, *args, **kwargs):
        self.default_log_values.update(update_gstr_action=True)
        return self._request("post", *args, **kwargs)

    def put(self, *args, **kwargs):
        self.default_log_values.update(update_gstr_action=True)
        return self._request("put", *args, **kwargs)

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

    def encrypt_request(self, json):
        if not json:
            return

        super().encrypt_request(json)

        if json.get("data"):
            b64_data = b64encode(frappe.as_json(json.get("data")).encode())
            json["data"] = aes_encrypt_data(b64_data.decode(), self.session_key)

            if json.get("st") == "EVC":
                sid_key = json.get("sid").encode()
                json["sign"] = hmac_sha256(b64_data, sid_key)

            else:
                json["hmac"] = hmac_sha256(b64_data, self.session_key)

    def handle_error_response(self, response):
        success_value = response.get("status_cd") != 0

        if not success_value and not self.is_ignored_error(response):
            frappe.throw(
                response.get("error", {}).get("message")
                # Fallback to response body if message is not present
                or frappe.as_json(response, indent=4),
                title=_("API Request Failed"),
            )

        # Handle invalid public key
        if response.error_type == "invalid_public_key":
            StaticResourcesAPI().get_gstn_public_certificate(
                error_message=_(
                    "Looks like Public Key of GSTN used for encryption is Invalid"
                )
            )

    def is_ignored_error(self, response):
        error_code = response.get("error", {}).get("error_cd")

        if error_code in self.IGNORED_ERROR_CODES:
            response.error_type = self.IGNORED_ERROR_CODES[error_code]
            response.gstin = self.company_gstin

            if response.error_type == "otp_requested":
                raise OTPRequestedError(response=response)

            if response.error_type == "invalid_otp":
                raise InvalidOTPError(response=response)

            return True

        return False

    def get_files(self, return_period, token, action, endpoint):
        response = self.get(
            action=action,
            return_period=return_period,
            params={"ret_period": return_period, "token": token},
            endpoint=endpoint,
        )

        if response.error_type == "queued":
            return response

        return FilesAPI().get_all(response)

    def validate_auth_token(self):
        """
        Try refreshing the auth token without error
        to check if the auth token is valid

        Generates a new OTP if the auth token is invalid
        """
        if frappe.cache.get_value(f"authenticated_gstin:{self.company_gstin}"):
            return

        # Dummy request
        self.fetch_filing_preference(fy=self.get_fy())

        frappe.cache.set_value(
            f"authenticated_gstin:{self.company_gstin}",
            True,
            expires_in_sec=60 * 15,
        )

        return

    def fetch_filing_preference(self, fy):
        return self.get(
            action="GETPREF", params={"fy": fy}, endpoint="returns"
        ).response

    @staticmethod
    def get_fy():
        date = frappe.utils.getdate()

        # Standard for India as per GST
        if date.month < 4:
            return f"{date.year - 1}-{str(date.year)[2:]}"

        return f"{date.year}-{str(date.year + 1)[2:]}"
