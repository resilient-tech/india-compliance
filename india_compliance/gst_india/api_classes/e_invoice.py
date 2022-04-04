import frappe
from frappe import _

from india_compliance.gst_india.api_classes.base import BaseAPI


class EInvoiceAPI(BaseAPI):
    def setup(self, company_gstin=None):
        self.api_name = "e-Invoice"
        self.base_path = "ei/api"

        if self.sandbox:
            company_gstin = "01AMBPG7773M002"
            self.username = "adqgspjkusr1"
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
            }
        )

    def handle_failed_response(self, response_json):
        # Don't fail in case of Duplicate IRN
        if response_json.get("message").startswith("2150"):
            return True

    def get_e_invoice_by_irn(self, irn):
        return self.get(endpoint="invoice/irn", params={"irn": irn})

    def generate_irn(self, data):
        return self.post(endpoint="invoice", json=data)

    def cancel_irn(self, data):
        return self.post(endpoint="invoice/cancel", json=data)

    def generate_e_waybill(self, data):
        return self.post(endpoint="ewaybill", json=data)

    def cancel_e_waybill(self, data):
        return self.post(endpoint="ewayapi", json=data)
