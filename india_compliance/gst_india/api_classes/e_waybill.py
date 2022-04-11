import frappe
from frappe import _

from india_compliance.gst_india.api_classes.base import BaseAPI


class EWaybillAPI(BaseAPI):
    def setup(self, company_gstin=None):
        self.api_name = "e-Waybill"
        self.base_path = "ewb/ewayapi"

        if self.sandbox:
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
        return self.post("GENEWAYBILL", data)

    def cancel_e_waybill(self, data):
        return self.post("CANEWB", data)

    def update_vehicle_info(self, data):
        return self.post("VEHEWB", data)

    def update_transporter(self, data):
        return self.post("UPDATETRANSPORTER", data)

    def extend_validity(self, data):
        return self.post("EXTENDVALIDITY", data)
