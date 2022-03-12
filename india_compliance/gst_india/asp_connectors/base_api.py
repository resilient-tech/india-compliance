import requests
from urllib.parse import urljoin

import frappe

from india_compliance.gst_india.asp_connectors.utils import create_request_log

BASE_URL = "https://asp.resilient.tech"


class BaseAPI:
    IGNORED_ERROR_CODES = set()

    def __init__(self):
        self.api_endpoint = None
        self.settings = frappe.get_doc("GST Settings")
        self.api_secret = self.settings.get_password("api_secret")
        self.default_headers = {"x-api-key": self.api_secret}

    def fetch_credentials(self, gstin, service):
        for creds in self.settings.credentials:
            if creds.gstin == gstin and creds.service == service:
                self.username = creds.username
                self.company = creds.company
                self.password = creds.get_password(raise_exception=False)
                break
        else:
            frappe.throw(
                f"You have not set credentials in GST Settings. Kindly set your {service} credentials to use API service.",
                title="Credentials unavailable",
            )

    def get_url(self, *parts):
        if self.api_endpoint:
            parts = (self.api_endpoint,) + parts

        return urljoin(BASE_URL, "/".join(part.strip("/") for part in parts))

    def get(self, *args, **kwargs):
        return self._make_request(method="GET", *args, **kwargs)

    def post(self, *args, **kwargs):
        return self._make_request(method="POST", *args, **kwargs)

    def _make_request(
        self, method, url=None, endpoint=None, params=None, headers={}, body=None
    ):
        method = method.upper()
        if method not in ("GET", "POST"):
            frappe.throw(f"Invalid method {method}")

        if not url:
            url = self.get_url(endpoint)

        headers = {**self.default_headers, **headers}
        if headers.pop("attach_request_id", None):
            headers["requestid"] = self.generate_request_id()

        log = frappe._dict()
        try:
            args = dict(url=url, params=params, headers=headers)
            print("args: ", args)
            if method == "POST":
                args["body"] = body

            response = getattr(requests, method.lower())(**args)
            log.request_id = response.headers.get("x-amzn-RequestId")

            log.request = {
                **args,
                "x-amzn-RequestId": log.request_id,
            }

            response.raise_for_status()
            response = response.json()

            log["response" if response.get("success") else "error"] = response

        except Exception as e:
            log.error = str(e)
            if isinstance(e, requests.RequestException) and e.response:
                log.error = e.response.json()

        finally:
            self.log(**log)
            self.handle_error(log.error)

        return frappe._dict(log.response.get("result") or log.response)

    def handle_error(self, error):
        if not error:
            return

        # save logs before throwing the error
        frappe.db.commit()

        if not isinstance(error, dict):
            frappe.throw(str(error))

        message = error.get("error_description", error.get("message", ""))
        error_code = error.get("errorCode")
        if error_code:
            if error_code in self.IGNORED_ERROR_CODES:
                return

            message = message.rstrip(".") + f". Error Code: {error_code}"

        frappe.throw(message)

    def log(self, *args, **kwargs):
        create_request_log(*args, **kwargs)

    def generate_request_id(self, length=12):
        return frappe.generate_hash(length=length)
