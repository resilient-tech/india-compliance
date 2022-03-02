import json
import random
from requests import api
import string

import frappe


class AuthApi:
    BASE_URL = "https://asp.resilient.tech/"

    def __init__(self):
        self.settings = frappe.get_doc("GST Settings")
        self.api_secret = self.settings.get_password("api_secret")

    def log_response(
        self, response=None, data=None, doctype=None, docname=None, error=None, request_id=None
    ):
        request_log = frappe.get_doc(
            {
                "doctype": "Integration Request",
                "integration_type": "Remote",
                "integration_request_service": f"GST India - {request_id}",
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
        url = self.BASE_URL + self.api_name + url_suffix
        if method == "get":
            response = api.get(url, params=params, headers=headers)
        else:
            response = api.post(url, params=params, headers=headers, data=data)

        self.mask_secret(headers)

        x_amzn_requestid = response.headers.get('x-amzn-RequestId')
        response = response.json()

        result = response.get("result") or response
        self.log_response(
            **{
                ("response" if result else "error"): response,
                "data": {
                    "url": url,
                    "headers": headers,
                    "body": data or "",
                    "params": params,
                    "x-amzn-RequestId": x_amzn_requestid
                },
                "request_id": x_amzn_requestid
            }
        )
        return response

    def mask_secret(self, headers):
        headers.update({key: "*****" for key in headers if key in ("x-api-key","password")})

    def generate_request_id(self, length=12):
        return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))
        