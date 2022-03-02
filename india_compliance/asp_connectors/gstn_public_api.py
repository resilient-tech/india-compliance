import frappe
from india_compliance.asp_connectors.auth_api import AuthApi


class GstnPublicApi(AuthApi):
    def __init__(self):
        super().__init__()
        self.api_name = "enriched/commonapi/"
        self.comp_gstin = self.settings.gst_credentials[0].gstin

    def get_params(self, action, gstin, fy=None):
        return {
            "action": action,
            "gstin": gstin,
            "fy": fy,
        }

    def get_headers(self):
        return {"x-api-key": self.settings.get_password('api_secret'), "gstin": self.comp_gstin}

    def make_get_request(self, urlsuffix, *args, **kwargs):
        response = self.make_request(
            method="get",
            url_suffix=urlsuffix,
            params=self.get_params(*args, **kwargs),
            headers=self.get_headers(),
        )
        return frappe._dict(response)

    def get_gstin_info(self, gstin):
        return self.make_get_request("search?", "TP", gstin)

    def get_returns_info(self, gstin, fy):
        if len(fy) == 9:
            start, end = fy.split("-")
            fy = f"{start}-{end[-2:]}"
        return self.make_get_request("returns?", "RETTRACK", gstin, fy=fy)
