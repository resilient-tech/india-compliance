import frappe
from frappe import _

from india_compliance.gst_india.api_classes.base import BaseAPI


class PublicAPI(BaseAPI):
    API_NAME = "GST Public"
    BASE_PATH = "commonapi"

    def setup(self):
        if self.sandbox_mode:
            frappe.throw(
                _(
                    "Autofill Party Information based on GSTIN is not supported in sandbox mode"
                )
            )
        self.default_headers.update({"requestid": self.generate_request_id()})

    def get_gstin_info(self, gstin):
        response = self.get("search", params={"action": "TP", "gstin": gstin})
        if self.sandbox_mode:
            response.update(
                {
                    "tradeNam": "Resilient Tech",
                    "lgnm": "Resilient Tech",
                }
            )

        return response
