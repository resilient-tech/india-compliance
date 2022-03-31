from india_compliance.gst_india.api_classes.base import BaseAPI


class EInvoiceAPI(BaseAPI):
    def setup(self, company_gstin):
        self.base_path = "ei/api"
        self.fetch_credentials(company_gstin, "e-Invoice")
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

    def generate_eway_bill(self, data):
        return self.post(endpoint="ewaybill", json=data)
