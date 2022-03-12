from india_compliance.gst_india.asp_connectors.base_api import BaseAPI


class EWaybillAPI(BaseAPI):
    def __init__(self, company_gstin):
        super().__init__()

        self.api_endpoint = "ewb/ewayapi"
        self.company_gstin = company_gstin
        self.fetch_credentials(self.company_gstin, "e-Waybill")
        self.default_headers.update(
            {
                "gstin": self.company_gstin,
                "username": self.username,
                "password": self.password,
                "attach_request_id": True,
            }
        )

    def post(self, action, body):
        return super().post(params={"action": action}, body=body)

    def get_ewaybill(self, ewaybill_number):
        return self.get(endpoint="getewaybill", params={"ewbNo": ewaybill_number})

    def generate_ewaybill(self, data):
        return self.post("GENEWAYBILL", data)

    def cancel_ewaybill(self, data):
        return self.post("CANEWB", data)

    def update_vehicle_info(self, data):
        return self.post("VEHEWB", data)

    def update_transporter(self, data):
        return self.post("UPDATETRANSPORTER", data)

    def extend_validity(self, data):
        return self.post("EXTENDVALIDITY", data)
