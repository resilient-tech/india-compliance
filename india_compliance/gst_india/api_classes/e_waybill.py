import re

import frappe
from frappe import _

from india_compliance.gst_india.api_classes.base import BaseAPI
from india_compliance.gst_india.constants import DISTANCE_REGEX


class EWaybillAPI(BaseAPI):
    API_NAME = "e-Waybill"
    BASE_PATH = "ewb/ewayapi"
    SENSITIVE_HEADERS = BaseAPI.SENSITIVE_HEADERS + ("password",)

    def setup(self, doc=None, *, company_gstin=None):
        if not self.settings.enable_e_waybill:
            frappe.throw(_("Please enable e-Waybill features in GST Settings first"))

        if doc:
            company_gstin = doc.company_gstin
            self.default_log_values.update(
                reference_doctype=doc.doctype,
                reference_name=doc.name,
            )

        if self.sandbox_mode:
            company_gstin = "05AAACG2115R1ZN"
            self.username = "05AAACG2115R1ZN"
            self.password = "abc123@@"

        elif not company_gstin:
            frappe.throw(_("Company GSTIN is required to use the e-Waybill API"))

        else:
            self.fetch_credentials(company_gstin, "e-Waybill / e-Invoice")

        self.default_headers.update(
            {
                "gstin": company_gstin,
                "username": self.username,
                "password": self.password,
            }
        )

    def post(self, action, json):
        return super().post(params={"action": action}, json=json)

    def get_e_waybill(self, ewaybill_number):
        return self.get("getewaybill", params={"ewbNo": ewaybill_number})

    def generate_e_waybill(self, data):
        result = self.post("GENEWAYBILL", data)
        self.update_distance(result)
        return result

    def cancel_e_waybill(self, data):
        return self.post("CANEWB", data)

    def update_vehicle_info(self, data):
        return self.post("VEHEWB", data)

    def update_transporter(self, data):
        return self.post("UPDATETRANSPORTER", data)

    def extend_validity(self, data):
        return self.post("EXTENDVALIDITY", data)

    def update_distance(self, result):
        if (
            (alert := result.get("alert"))
            and "Distance" in alert
            and (distance_match := re.search(DISTANCE_REGEX, alert))
        ):
            result.distance = int(distance_match.group())
