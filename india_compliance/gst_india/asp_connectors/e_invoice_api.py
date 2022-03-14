from india_compliance.gst_india.asp_connectors.base_api import BaseAPI


class EInvoiceAPI(BaseAPI):
    def __init__(self, company_gstin):
        super().__init__()

        self.api_endpoint = "ei/api"
        self.company_gstin = company_gstin
        self.fetch_credentials(self.company_gstin, "e-Invoice")
        self.default_headers.update(
            {
                "user_name": self.username,
                "password": self.password,
                "gstin": self.company_gstin,
                "attach_request_id": True,
            }
        )

    def handle_error(self, error):
        if isinstance(error, dict) and "2150" in error.get("message", ""):
            return

        return super().handle_error(error)

    def get_e_invoice_by_irn(self, irn):
        return self.get(endpoint="invoice/irn", params={"irn": irn})

    def generate_irn(self, data):
        return self.post(endpoint="invoice", body=data)

    def cancel_irn(self, data):
        return self.post(endpoint="invoice/cancel", body=data)

    def generate_eway_bill(self, data):
        return self.post(endpoint="ewaybill", body=data)
