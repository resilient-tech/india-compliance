import json
import frappe

from india_compliance.asp_connectors.auth_api import AuthApi


class GstnEwbApi(AuthApi):
    def __init__(self, company_gstin):
        super().__init__()
        self.api_name = "enriched/ewb/"
        self.url_suffix = "ewayapi?"
        self.comp_gstin = company_gstin
        for creds in self.settings.gst_credentials:
            if creds.gstin == company_gstin and creds.service == "EwayBill":
                self.username = creds.username
                self.password = creds.get_password("password")
                break

        # sandbox
        if self.settings.sandbox:
            self.comp_gstin = self.username = "05AAACG2115R1ZN"
            self.password = "abc123@@"

        if not self.username:
            frappe.throw(
                "You have not set credentials in GST Settings. Kindly set your EwayBill credentials to use API service.",
                title="Credentials unavailable",
            )

    def get_headers(self):
        return {
            "requestid": self.generate_request_id(),
            "gstin": self.comp_gstin,
            "username": self.username,
            "password": self.password,
            "x-api-key": self.settings.get_password('api_secret'),
        }

    def get_ewaybill(self, ewbNo):
        response = self.make_request(
            method="get",
            url_suffix="ewayapi/GetEwayBill?",
            params={"ewbNo": ewbNo},
            headers=self.get_headers(),
        )
        return frappe._dict(response)

    # generate post methods with different actions.
    def make_post_request(self, action, data):
        data = json.dumps(data)
        response = self.make_request(
            method="post",
            url_suffix=self.url_suffix,
            params={"action": action},
            headers=self.get_headers(),
            data=data,
        )
        return frappe._dict(response)

    def generate_ewaybill(self, data):
        return self.make_post_request("GENEWAYBILL", data)

    def update_vehicle_info(self, data):
        return self.make_post_request("VEHEWB", data)

    def update_transporter(self, data):
        return self.make_post_request("UPDATETRANSPORTER", data)

    def extend_validity(self, data):
        return self.make_post_request("EXTENDVALIDITY", data)

    def cancel_ewaybill(self, data):
        return self.make_post_request("CANEWB", data)
