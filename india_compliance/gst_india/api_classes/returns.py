from india_compliance.gst_india.api_classes.base import BaseAPI


class ReturnsAPI(BaseAPI):
    IGNORED_ERROR_CODES = {
        "RETOTPREQUEST": "otp_requested",
        "EVCREQUEST": "otp_requested",
        "RET11416": "no_docs_found",
        "RET13508": "no_docs_found",
        "RET13509": "no_docs_found",
        "RET13510": "no_docs_found",
        "RET2B1023": "no_docs_found",
        "RET2B1016": "no_docs_found",
        "RT-3BAS1009": "no_docs_found",
    }

    def setup(self, company_gstin):
        self.company_gstin = company_gstin
        self.fetch_credentials(self.company_gstin, "Returns")
        self.default_headers.update(
            {
                "gstin": self.company_gstin,
                "state-cd": self.company_gstin[:2],
                "username": self.username,
            }
        )

    def handle_failed_response(self, response_json):
        if response_json.get("errorCode") in self.IGNORED_ERROR_CODES:
            return True

    def get(self, action, return_period, otp=None, params=None):
        response = super().get(
            params={"action": action, "gstin": self.company_gstin, **(params or {})},
            headers={
                "requestid": self.generate_request_id(),
                "ret_period": return_period,
                "otp": otp,
            },
        )

        if error_type := self.IGNORED_ERROR_CODES.get(response.errorCode):
            response.error_type = error_type

        return response


class GSTR_2B_API(ReturnsAPI):
    def setup(self, company_gstin):
        super().setup(company_gstin)
        self.base_path = "returns/gstr2b"

    def get_data(self, return_period, otp=None):
        # TODO: Create further calls if more than one file to download
        return self.get("GET2B", return_period, otp, {"rtnprd": return_period})


class GSTR_2A_API(ReturnsAPI):
    def setup(self, company_gstin):
        super().setup(company_gstin)
        self.base_path = "returns/gstr2a"

    def get_data(self, action, return_period, otp=None):
        # TODO: Create further calls if more than one file to download
        return self.get(action, return_period, otp, {"ret_period": return_period})
