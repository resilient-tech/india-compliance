from india_compliance.gst_india.asp_connectors.base_api import BaseAPI


class ReturnsAPI(BaseAPI):
    def __init__(self, company_gstin):
        super().__init__()
        self.comp_gstin = company_gstin
        self.fetch_credentials(self.comp_gstin, "Returns")
        self.set_defaults()

    def set_defaults(self):
        self.otp_requested_error_codes = {"RETOTPREQUEST", "EVCREQUEST"}
        self.no_docs_found_error_codes = {
            "RET11416",
            "RET13508",
            "RET13509",
            "RET13510",
            "RET2B1023",
            "RET2B1016",
            "RT-3BAS1009",
        }
        self.IGNORE_ERROR_CODES = self.otp_requested_error_codes.union(
            self.no_docs_found_error_codes
        )

        self.default_headers.update(
            {
                "username": self.username,
                "state-cd": self.comp_gstin[:2],
                "gstin": self.comp_gstin,
            }
        )

    def get(self, action, return_period, otp=None, params={}):
        response = super().get(
            params={"action": action, "gstin": self.comp_gstin, **params},
            headers={
                "requestid": self.generate_request_id(),
                "ret_period": return_period,
                "otp": otp,
            },
        )

        if response.errorCode in self.otp_requested_error_codes:
            response.otp_requested = True

        elif response.errorCode in self.no_docs_found_error_codes:
            response.no_docs_found = True

        return response


class GSTR2bAPI(ReturnsAPI):
    def __init__(self, company_gstin):
        super().__init__(company_gstin)
        self.api_endpoint = "returns/gstr2b"

    def get_gstr_2b(self, return_period, otp=None):
        return self.get("GET2B", return_period, otp, {"rtnprd": return_period})
        # TODO: Create further calls if more than one file to download


class GSTR2aAPI(ReturnsAPI):
    def __init__(self, company_gstin):
        super().__init__(company_gstin)
        self.api_endpoint = "returns/gstr2a"

    def get_gstr_2a(self, action, return_period, otp=None):
        return self.get(action, return_period, otp, {"ret_period": return_period})
