import re

import frappe
from frappe import _

from india_compliance.gst_india.api_classes.base import BaseAPI, check_scheduler_status
from india_compliance.gst_india.constants import DISTANCE_REGEX


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
