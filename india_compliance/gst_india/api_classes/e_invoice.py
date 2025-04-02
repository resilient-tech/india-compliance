import base64
import re
from datetime import datetime

from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.serialization import load_pem_public_key

import frappe
from frappe import _

from india_compliance.gst_india.api_classes.base import BaseAPI, check_scheduler_status
from india_compliance.gst_india.api_classes.taxpayer_base import StaticResourcesAPI
from india_compliance.gst_india.constants import DISTANCE_REGEX
from india_compliance.gst_india.utils.cryptography import (
    aes_decrypt_data,
    aes_encrypt_data,
)


class NICAuth(BaseAPI):
    def setup(self, doc=None, *, company_gstin=None):
        self.company_gstin = company_gstin

        self.validate_enable_api()
        check_scheduler_status()

        if doc:
            self.company_gstin = doc.company_gstin
            self.default_log_values.update(
                reference_doctype=doc.doctype,
                reference_name=doc.name,
            )

        if not self.company_gstin:
            frappe.throw(_("Company GSTIN is required to use the e-Invoice API"))

        else:
            self.fetch_credentials(self.company_gstin, "e-Waybill / e-Invoice")

        self.set_default_headers()

    def _fetch_credentials(self, row, require_password=True):
        self.password = row.get_password(raise_exception=require_password)
        self.app_key = self.get_app_key(row)
        self.session_key = base64.b64decode(row.session_key or "")
        self.session_expiry = row.session_expiry
        self.auth_token = row.auth_token

    def validate_enable_api(self):
        pass

    def get_app_key(self, row):
        return row.app_key or self.generate_app_key()

    def generate_app_key(self):
        app_key = frappe.generate_hash(length=32)

        frappe.db.set_value(
            "GST Credential",
            {
                "gstin": self.company_gstin,
                "username": self.username,
                "service": "e-Waybill / e-Invoice",
            },
            {"app_key": app_key},
        )

        return app_key

    def before_request(self, request_args):
        self.encrypt_request(request_args)

    def process_response(self, response):
        self.handle_error_response(response)
        self.decrypt_response(response)
        self.response = response
        return response

    def get_public_key(self):
        key = self.settings.nic_public_key
        if not key:
            key = StaticResourcesAPI().get_nic_public_key()

        return key.encode()

    def is_authentication_api(self, request_args):
        return request_args.get("url").endswith("auth")

    def encrypt_request(self, request_args):
        if not (json_data := request_args.get("json")):
            return

        json_data = json_data.get("Data")

        if not json_data:
            return

        json_data = frappe.as_json(json_data)
        json_data = base64.b64encode(json_data.encode())

        encrypted_json = encrypt_using_public_key(
            json_data,
            self.get_public_key(),
        )

        request_args["json"]["Data"] = encrypted_json

    def decrypt_response(self, response):
        pass

    def is_authenticated(self):
        return (
            all(
                getattr(self, attr, None)
                for attr in ["auth_token", "session_key", "session_expiry"]
            )
            and self.session_expiry >= datetime.now()
        )

    def authenticate(self):
        pass

    def set_default_headers(self):
        pass


class EInvoiceAPI(BaseAPI):
    API_NAME = "e-Invoice"
    SENSITIVE_INFO = BaseAPI.SENSITIVE_INFO + ("password",)
    IGNORED_ERROR_CODES = {
        # Generate IRN errors
        "2150": "Duplicate IRN",
        # Get e-Invoice by IRN errors
        "2283": (
            "IRN details cannot be provided as it is generated more than 2 days ago"
        ),
        # Cancel IRN errors
        "9999": "Invoice is not active",
        "4002": "EwayBill is already generated for this IRN",
        # IRN Generated in different Portal
        "2148": "Requested IRN data is not available",
        # Invalid GSTIN error
        "3028": "GSTIN is invalid",
        "3029": "GSTIN is not active",
        "3001": "Requested data is not available",
    }

    def __new__(cls, *args, **kwargs):
        if cls != EInvoiceAPI:
            return super().__new__(cls)

        sandbox_mode = frappe.db.get_single_value("GST Settings", "sandbox_mode")

        if sandbox_mode:
            return EnrichedEInvoiceAPI(*args, **kwargs)

        return StandardEInvoiceAPI(*args, **kwargs)

    def get_e_invoice_by_irn(self, irn):
        return self.get(endpoint="invoice/irn", params={"irn": irn})

    def get_e_waybill_by_irn(self, irn):
        return self.get(endpoint="ewaybill/irn", params={"irn": irn})

    def generate_irn(self, data):
        result = self.post(endpoint="invoice", json=data)

        # In case of Duplicate IRN, result is a list
        if isinstance(result, list):
            result = result[0]

        self.update_distance(result)
        return result

    def cancel_irn(self, data):
        return self.post(endpoint="invoice/cancel", json=data)

    def generate_e_waybill(self, data):
        result = self.post(endpoint="ewaybill", json=data)
        self.update_distance(result)
        return result

    def cancel_e_waybill(self, data):
        return self.post(endpoint="ewayapi", json=data)

    def update_distance(self, result):
        if not (info := self.response.get("info")):
            return

        alert = next((alert for alert in info if alert.get("InfCd") == "EWBPPD"), None)

        if (
            alert
            and (description := alert.get("Desc"))
            and (distance_match := re.search(DISTANCE_REGEX, description))
        ):
            result.distance = int(distance_match.group())

    def get_gstin_info(self, gstin):
        return self.get(endpoint="master/gstin", params={"gstin": gstin})

    def sync_gstin_info(self, gstin):
        return self.get(endpoint="master/syncgstin", params={"gstin": gstin})


class EnrichedEInvoiceAPI(EInvoiceAPI):
    BASE_PATH = "ei/api"

    def setup(self, doc=None, *, company_gstin=None):
        if not self.settings.enable_e_invoice:
            frappe.throw(_("Please enable e-Invoicing in GST Settings first"))

        check_scheduler_status()

        if doc:
            company_gstin = doc.company_gstin
            self.default_log_values.update(
                reference_doctype=doc.doctype,
                reference_name=doc.name,
            )

        if self.sandbox_mode:
            company_gstin = "02AMBPG7773M002"
            self.username = "adqgsphpusr1"
            self.password = "Gsp@1234"

        elif not company_gstin:
            frappe.throw(_("Company GSTIN is required to use the e-Invoice API"))

        else:
            self.fetch_credentials(company_gstin, "e-Waybill / e-Invoice")

        self.default_headers.update(
            {
                "gstin": company_gstin,
                "user_name": self.username,
                "password": self.password,
                "requestid": self.generate_request_id(),
            }
        )

    def is_ignored_error(self, response_json):
        message = response_json.get("message", "").strip()

        for error_code in self.IGNORED_ERROR_CODES:
            if message.startswith(error_code):
                response_json.error_code = error_code
                return True


class EInvoiceAuth(NICAuth):
    IGNORED_ERROR_CODES = {}

    def validate_enable_api(self):
        if self.settings.enable_e_invoice:
            return

        frappe.throw(_("Please enable e-Invoicing in GST Settings first"))

    def get_app_key(self, row):
        app_key = row.app_key or self.generate_app_key()
        return base64.b64encode(app_key.encode()).decode()

    def decrypt_response(self, response):
        values = {}
        response_data = response.get("Data")

        if not response_data:
            return response

        if response_data.get("AuthToken"):
            self.auth_token = response_data.AuthToken
            values["auth_token"] = response_data.AuthToken

        if response_data.get("TokenExpiry"):
            # TokenExpiry is like '2025-02-06 18:41:48'
            session_expiry = datetime.strptime(
                response_data.TokenExpiry, "%Y-%m-%d %H:%M:%S"
            )
            self.session_expiry = session_expiry
            values["session_expiry"] = session_expiry

        if response_data.get("Sek"):
            session_key = aes_decrypt_data(
                response_data.Sek, base64.b64decode(self.app_key.encode())
            )
            self.session_key = session_key
            values["session_key"] = base64.b64encode(session_key).decode()

        if values:
            frappe.db.set_value(
                "GST Credential",
                {
                    "gstin": self.company_gstin,
                    "username": self.username,
                    "service": "e-Waybill / e-Invoice",
                },
                values,
            )

            # cache of parent doctype GST Settings is not cleared by default so clear it manually
            frappe.clear_document_cache("GST Settings")

        return response

    def authenticate(self):
        json_data = {
            "Data": {
                "UserName": self.username,
                "Password": self.password,
                "AppKey": self.app_key,
                "ForceRefreshAccessToken": False,
            }
        }

        return self.post(endpoint="auth", json=json_data)


class StandardEInvoiceAPI(EInvoiceAuth, EInvoiceAPI):
    BASE_PATH = "standard/ei/api"

    def setup(self, doc=None, *, company_gstin=None):
        super().setup(doc, company_gstin=company_gstin)

        if not self.is_authenticated():
            self.authenticate()

    def set_default_headers(self):
        self.default_headers.update(
            {
                "gstin": self.company_gstin,
                "user_name": self.username,
                "password": self.password,
                "requestid": self.generate_request_id(),
            }
        )

    def handle_error_response(self, response):
        success_value = response.get("Status") != 0
        if not success_value and not self.is_ignored_error(response):
            frappe.throw(
                response.get("ErrorDetails", {})[0].get("ErrorMessage")
                # Fallback to response body if message is not present
                or frappe.as_json(response, indent=4),
                title=_("API Request Failed"),
            )

    def is_ignored_error(self, response):
        error_details = response.get("ErrorDetails")

        if not error_details:
            return

        for error_code in self.IGNORED_ERROR_CODES:
            if error_code == error_details[0].get("ErrorCode"):
                response.error_code = error_code
                return True

    def before_request(self, request_args):
        self.encrypt_request(request_args)

        if self.is_authentication_api(request_args):
            return

        request_args["headers"]["AuthToken"] = self.auth_token

    def encrypt_request(self, request_args):
        if self.is_authentication_api(request_args):
            return super().encrypt_request(request_args)

        if not (json_data := request_args.get("json")):
            return

        encrypted_data = aes_encrypt_data(frappe.as_json(json_data), self.session_key)

        request_args["json"] = {
            "Data": encrypted_data,
        }

    def decrypt_response(self, response):
        if response.get("error_code"):
            return response

        if not (response_data := response.get("Data")):
            return response

        if not isinstance(response_data, str):
            return super().decrypt_response(response)

        decrypted_data = aes_decrypt_data(response_data, self.session_key)
        response.result = frappe.parse_json(decrypted_data.decode())

        return response


def encrypt_using_public_key(data: str, public_key: bytes) -> str:
    public_key = load_pem_public_key(public_key)

    encrypted_msg = public_key.encrypt(plaintext=data, padding=asym_padding.PKCS1v15())
    encoded_encrypted_msg = base64.b64encode(encrypted_msg).decode()

    return encoded_encrypted_msg
