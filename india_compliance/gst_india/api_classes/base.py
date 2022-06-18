import copy
from urllib.parse import urljoin

import requests

import frappe
from frappe import _
from frappe.utils import sbool

from india_compliance.gst_india.utils.api import enqueue_integration_request

BASE_URL = "https://asp.resilient.tech"


class BaseAPI:
    def __init__(self, *args, **kwargs):
        self.api_name = "GST"
        self.base_path = ""
        self.sandbox = frappe.conf.use_gst_api_sandbox or frappe.flags.in_test
        self.settings = frappe.get_cached_doc("GST Settings")
        self.default_headers = {
            "x-api-key": self.settings.get_password("api_secret"),
        }

        if not self.settings.enable_api:
            frappe.throw(
                _("Please enable API in GST Settings to use the {0} API").format(
                    self.api_name
                )
            )

        self.setup(*args, **kwargs)

    def setup(*args, **kwargs):
        # Override in subclass
        pass

    def fetch_credentials(self, gstin, service, require_password=True):
        for row in self.settings.credentials:
            if row.gstin == gstin and row.service == service:
                break
        else:
            frappe.throw(
                _(
                    "Please set the relevant credentials in GST Settings to use the"
                    " {0} API"
                ).format(self.api_name),
                frappe.DoesNotExistError,
                title=_("Credentials Unavailable"),
            )

        self.username = row.username
        self.company = row.company
        self.password = row.get_password(raise_exception=require_password)

    def get_url(self, *parts):
        parts = list(parts)

        if self.base_path:
            parts.insert(0, self.base_path)

        if self.sandbox:
            parts.insert(0, "test")

        return urljoin(BASE_URL, "/".join(part.strip("/") for part in parts))

    def get(self, *args, **kwargs):
        return self._make_request("GET", *args, **kwargs)

    def post(self, *args, **kwargs):
        return self._make_request("POST", *args, **kwargs)

    def _make_request(
        self,
        method,
        endpoint="",
        params=None,
        headers=None,
        json=None,
    ):
        method = method.upper()
        if method not in ("GET", "POST"):
            frappe.throw(_("Invalid method {0}").format(method))

        request_args = frappe._dict(
            url=self.get_url(endpoint),
            params=params,
            headers={
                # auto-generated hash, required by some endpoints
                "requestid": self.generate_request_id(),
                **self.default_headers,
                **(headers or {}),
            },
        )

        if method == "POST":
            request_args.json = json

        response_json = None
        log = frappe._dict()

        # TODO: change after fields created in Frappe
        log.data = copy.deepcopy(request_args)

        # Don't log API secret
        log.data["headers"].pop("x-api-key", None)

        try:
            response = requests.request(method, **request_args)
            if api_request_id := response.headers.get("x-amzn-RequestId"):
                log.data["api_request_id"] = api_request_id

            try:
                response_json = response.json()
            except Exception:
                pass

            # Raise special error for certain HTTP codes
            self.handle_http_code(response.status_code, response_json)

            # Raise HTTPError for other HTTP codes
            response.raise_for_status()

            # Expect all successful responses to be JSON
            if not response_json:
                frappe.throw(_("Error parsing response: {0}").format(response.content))

            # All error responses have a success key set to false
            success_value = response_json.get("success", True)
            if isinstance(success_value, str):
                success_value = sbool(success_value)

            if not success_value and not self.handle_failed_response(response_json):
                frappe.throw(
                    response_json.get("message")
                    # Fallback to response body if message is not present
                    or frappe.as_json(response_json, indent=4),
                    title=_("API Request Failed"),
                )

            return self.handle_success_response(response_json)

        except Exception as e:
            log.error = str(e)
            raise e

        finally:
            log.output = response_json
            enqueue_integration_request(**log)

    def handle_failed_response(self, response_json):
        # Override in subclass, return truthy value to stop frappe.throw
        pass

    def handle_success_response(self, response_json):
        return frappe._dict(response_json)

    def handle_http_code(self, status_code, response_json):
        # TODO: add link to account page / support email

        # GSP connectivity issues
        if status_code == 401 or (
            status_code == 403
            and response_json
            and response_json.get("error") == "access_denied"
        ):
            frappe.throw(
                _(
                    "Error establishing connection to GSP. "
                    "Please contact India Compliance API Support."
                ),
                title=_("GSP Connection Error"),
            )

        # ASP connectivity issues
        if status_code == 429:
            frappe.throw(
                _("Your India Compliance API credits have exhausted"),
                title=_("API Credits Exhausted"),
            )

        if status_code == 403:
            frappe.throw(
                _("Your India Compliance API key is invalid"),
                title=_("Invalid API Key"),
            )

    def generate_request_id(self, length=12):
        return frappe.generate_hash(length=length)
