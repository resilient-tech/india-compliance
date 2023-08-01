from india_compliance.gst_india.api_classes.base import BaseAPI


class ReturnsAPI(BaseAPI):
    API_NAME = "GST Returns"
    BASE_PATH = "returns"
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
        "RET2B1018": "requested_before_cutoff_date",
        "RETINPROGRESS": "queued",
    }

    def setup(self, company_gstin):
        self.company_gstin = company_gstin
        self.fetch_credentials(self.company_gstin, "Returns", require_password=False)
        self.default_headers.update(
            {
                "gstin": self.company_gstin,
                "state-cd": self.company_gstin[:2],
                "username": self.username,
            }
        )

    def handle_failed_response(self, response_json):
        for error_code, error_message in self.IGNORED_ERROR_CODES.items():
            if response_json.get("errorCode") == error_code:
                response_json.error_type = error_message
                return True

    def get(self, action, return_period, otp=None, params=None, requestid=None):
        request_id = requestid or self.generate_request_id()
        response = super().get(
            params={"action": action, "gstin": self.company_gstin, **(params or {})},
            headers={
                "requestid": request_id,
                "ret_period": return_period,
                "otp": otp,
            },
        )

        response.requestid = request_id
        return response

    def get_return_status(self, return_period, requestid, otp=None):
        return self.get(
            "RETSTATUS", return_period, otp, {"ret_period": return_period}, requestid
        )


class GSTR2aAPI(ReturnsAPI):
    API_NAME = "GSTR-2A"
    BASE_PATH = "returns/gstr2a"

    def get_data(self, action, return_period, otp=None):
        # TODO: Create further calls if more than one file to download
        return self.get(action, return_period, otp, {"ret_period": return_period})


class GSTR2bAPI(ReturnsAPI):
    API_NAME = "GSTR-2B"
    BASE_PATH = "returns/gstr2b"

    def get_data(self, return_period, otp=None, file_num=None):
        return self.get(
            "GET2B", return_period, otp, {"rtnprd": return_period, "file_num": file_num}
        )
