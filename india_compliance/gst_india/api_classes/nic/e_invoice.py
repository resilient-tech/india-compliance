import base64
import re

import frappe
from frappe import _

from india_compliance.gst_india.api_classes.base import BaseAPI, check_scheduler_status
from india_compliance.gst_india.api_classes.nic.auth import EnrichedAuth, StandardAuth
from india_compliance.gst_india.constants import DISTANCE_REGEX


class EInvoiceAPI(BaseAPI):
    API_NAME = "e-Invoice"
    SENSITIVE_INFO = BaseAPI.SENSITIVE_INFO + ("password", "Password", "AppKey")
    IGNORED_ERROR_CODES = {
        "1005": "Invalid Token",
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

    # Response Keys
    AUTH_TOKEN_KEY = "AuthToken"
    USER_NAME_KEY = "UserName"
    PASSWORD_KEY = "Password"
    APP_KEY = "AppKey"
    DATA_KEY = "Data"
    SEK_KEY = "Sek"
    REK_KEY = "Rek"
    HMAC_KEY = "Hmac"

    @classmethod
    def create(cls, *args, **kwargs):
        if cls != EInvoiceAPI:
            return cls(*args, **kwargs)

        settings = frappe.get_cached_doc("GST Settings")

        if settings.sandbox_mode or settings.use_fallback_for_nic:
            return EnrichedEInvoiceAPI(*args, **kwargs)

        return StandardEInvoiceAPI(*args, **kwargs)

    def setup(self, doc=None, *, company_gstin=None):
        self.validate_enable_api()
        check_scheduler_status()

        if doc:
            self.company_gstin = doc.company_gstin
            self.default_log_values.update(
                reference_doctype=doc.doctype,
                reference_name=doc.name,
            )
        else:
            self.company_gstin = company_gstin

    def set_default_headers(self):
        self.default_headers.update(
            {
                "gstin": self.company_gstin,
                "user_name": self.username,
                "password": self.password,
                "requestid": self.generate_request_id(),
            }
        )

    def validate_enable_api(self):
        if self.settings.enable_e_invoice:
            return

        frappe.throw(_("Please enable e-Invoicing in GST Settings first"))

    def is_ignored_error(self, response_json):
        message = response_json.get("message", "").strip()

        for error_code in self.IGNORED_ERROR_CODES:
            if message.startswith(error_code):
                response_json.error_code = error_code
                return True

        return False

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
        if not (info := self.get_response_info()):
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

    def get_response_info(self):
        return None


class EnrichedEInvoiceAPI(EInvoiceAPI):
    BASE_PATH = "ei/api"

    def setup(self, doc=None, *, company_gstin=None):
        super().setup(doc, company_gstin=company_gstin)

        if self.sandbox_mode:
            self.company_gstin = "02AMBPG7773M002"
            self.username = "adqgsphpusr1"
            self.password = "Gsp@1234"
        else:
            self.fetch_credentials(self.company_gstin, "e-Waybill / e-Invoice")

        self.auth_strategy = EnrichedAuth(self)
        self.set_default_headers()

    def get_response_info(self):
        return self.response.get("info")


class StandardEInvoiceAPI(EInvoiceAPI):
    BASE_PATH = "standard/ei/api"

    def setup(self, doc=None, *, company_gstin=None):
        super().setup(doc, company_gstin=company_gstin)

        if not self.company_gstin:
            frappe.throw(_("Company GSTIN is required to use the e-Invoice API"))

        self.fetch_credentials(self.company_gstin, "e-Waybill / e-Invoice")
        self.app_key = base64.b64encode(self.app_key.encode()).decode()
        self.set_default_headers()

        self.auth_strategy = StandardAuth(self)
        self.auth_strategy.authenticate()

    def _make_request(self, method, endpoint="", params=None, headers=None, json=None):
        response = super()._make_request(method, endpoint, params, headers, json)

        # Invalid Token
        if response.error_code == "1005":
            self.auth_token = None
            self.auth_strategy.authenticate()
            response = super()._make_request(method, endpoint, params, headers, json)

        return response

    def authenticate(self):
        json_data = {
            self.USER_NAME_KEY: self.username,
            self.PASSWORD_KEY: self.password,
            self.APP_KEY: self.app_key,
            "ForceRefreshAccessToken": False,
        }

        return self.post(endpoint="auth", json=json_data)

    def handle_error_response(self, response_json):
        is_success = response_json.get("Status") != 0

        if is_success:
            return

        # extract errors
        error_messages = [
            f"{error.get('ErrorCode', '')}: {error.get('ErrorMessage', '')}"
            for error in response_json.get("ErrorDetails", [])
        ]
        self.handle_server_error(error_messages)

        if self.is_ignored_error(response_json):
            return

        # throw
        formatted_error_message = (
            ("<br>").join(error_messages)
            if error_messages
            else frappe.as_json(response_json, indent=4)
        )

        frappe.throw(
            _("Error generating e-Invoice:<br>{0}").format(formatted_error_message),
            title=_("API Request Failed"),
        )

    def is_ignored_error(self, response):
        error_details = response.get("ErrorDetails")

        if not error_details:
            return False

        error_code = error_details[0].get("ErrorCode")
        if error_code in self.IGNORED_ERROR_CODES:
            response.error_code = error_code
            return True

        return False

    def get_response_info(self):
        return self.response.get("InfoDtls")
