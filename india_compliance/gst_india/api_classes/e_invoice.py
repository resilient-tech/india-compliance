import json
import re
from datetime import datetime

from cryptography import x509
from cryptography.hazmat.backends import default_backend

import frappe
from frappe import _

from india_compliance.gst_india.api_classes.base import BaseAPI, check_scheduler_status
from india_compliance.gst_india.api_classes.taxpayer_base import PublicCertificate
from india_compliance.gst_india.constants import DISTANCE_REGEX
from india_compliance.gst_india.utils.cryptography import encrypt_using_public_key


class EInvoiceAPI(BaseAPI):
    API_NAME = "e-Invoice"
    BASE_PATH = "ei/api"
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
        # Invalid GSTIN error
        "3028": "GSTIN is invalid",
        "3029": "GSTIN is not active",
    }

    def setup(self, doc=None, *, company_gstin=None):
        if not self.settings.enable_e_invoice:
            frappe.throw(_("Please enable e-Invoicing in GST Settings first"))

        check_scheduler_status()

        self.company_gstin = company_gstin
        if doc:
            self.company_gstin = doc.company_gstin
            self.default_log_values.update(
                reference_doctype=doc.doctype,
                reference_name=doc.name,
            )

        if self.sandbox_mode:
            self.company_gstin = "02AMBPG7773M002"
            self.username = "adqgsphpusr1"
            self.password = "Gsp@1234"

        elif not self.company_gstin:
            frappe.throw(_("Company GSTIN is required to use the e-Invoice API"))

        else:
            self.fetch_credentials(self.company_gstin, "e-Waybill / e-Invoice")

        self.default_headers.update(
            {
                "gstin": self.company_gstin,
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


class EInvoiceAuth(EInvoiceAPI):
    API_NAME = "e-Invoice Auth"

    def _fetch_credentials(self, row, require_password=True):
        self.password = row.get_password(raise_exception=require_password)
        self.app_key = row.app_key or self.generate_app_key()

    def generate_app_key(self):
        app_key = self.generate_request_id(length=32)
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

    def encrypt_request(self, request_args):
        if not (json_data := request_args.get("json")):
            return

        json_data = json.dumps(json_data)

        encrypted_json = encrypt_using_public_key(
            json_data,
            self.get_public_certificate(),
        )

        request_args["json"] = {
            "data": encrypted_json,
        }

    def get_public_certificate(self):
        certificate = self.settings.einvoice_public_certificate

        if not certificate:
            certificate = PublicCertificate().get_einvoice_public_certificate()

        cert = x509.load_pem_x509_certificate(certificate.encode(), default_backend())
        valid_up_to = cert.not_valid_after

        if valid_up_to < datetime.now():
            certificate = PublicCertificate().get_einvoice_public_certificate()

        return certificate.encode()

    def authenticate(self):
        json = {
            "UserName": self.username,
            "Password": self.password,
            "AppKey": self.app_key,
            "ForceRefreshAccessToken": False,
        }

        return self.post(endpoint="auth", json=json)
