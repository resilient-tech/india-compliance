import json
import random
from requests import api
import string

import frappe


class AuthApi:
    BASE_URL = "https://asp.resilient.tech/"

    def __init__(self):
        self.settings = frappe.get_doc("GST Settings")
        self.test_url = "test/" if self.settings.sandbox else ""
        self.api_secret = self.settings.api_secret

    def log_response(
        self, response=None, data=None, doctype=None, docname=None, error=None
    ):
        request_log = frappe.get_doc(
            {
                "doctype": "Integration Request",
                "integration_type": "Remote",
                "integration_request_service": "GST India",
                "reference_doctype": doctype,
                "reference_docname": docname,
                "data": json.dumps(data, indent=4) if isinstance(data, dict) else data,
                "output": json.dumps(response, indent=4) if response else None,
                "error": json.dumps(error, indent=4) if error else None,
                "status": "Failed" if error else "Completed",
            }
        )
        request_log.insert(ignore_permissions=True)

        if error:
            frappe.db.commit()
            error_des = "{}{}{}".format(
                error.get("error_description", ""),
                error.get("message", ""),
                ". Error Code: " + error.get("errorCode")
                if error.get("errorCode")
                else "",
            )
            frappe.throw(error_des)

    def make_request(
        self,
        method,
        url_suffix,
        params,
        headers,
        data=None,
    ):
        if method not in ("get", "post"):
            frappe.throw("Invalid method", method.upper())

        # api calls
        url = self.BASE_URL + self.test_url + self.api_name + url_suffix
        if method == "get":
            response = api.get(url, params=params, headers=headers).json()
        else:
            response = api.post(url, params=params, headers=headers, data=data).json()

        result = ""
        if self.no_error_found(response):
            result = response.get("result") or response
        self.log_response(
            **{
                ("response" if result else "error"): response,
                "data": {
                    "headers": headers,
                    "body": data or "",
                    "params": params,
                },
            }
        )
        return result

    def generate_request_id(self, length=12):
        return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))

    def no_error_found(self, r):
        return self.success(r) or self.otp_required(r) or self.no_docs_found(r)

    def success(self, r):
        return (
            True
            if r.get("result") or r.get("success") not in ["false", "False", False]
            else False
        )

    def otp_required(self, r):
        return r.get("errorCode") == "RETOTPREQUEST"

    def no_docs_found(self, r):
        if not r.get("errorCode"):
            return

        no_docs_found = {
            "gstr_2b": ["RET2B1023", "RET2B1016"],
            "gstr_2a": ["RET13508", "RET13509", "RET13510"],
            "gstr_1": ["RET11416"],
            "gstr_3b": ["RT-3BAS1009"],
        }

        for ret in no_docs_found:
            if r.get("errorCode") in no_docs_found[ret]:
                return True
        return False
