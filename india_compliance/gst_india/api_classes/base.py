from urllib.parse import urljoin

import requests

import frappe
from frappe import _
from frappe.utils import sbool

from india_compliance.exceptions import GatewayTimeoutError, GSPServerError
from india_compliance.gst_india.utils import is_api_enabled
from india_compliance.gst_india.utils.api import enqueue_integration_request

BASE_URL = "https://asp.resilient.tech"


class BaseAPI:
    API_NAME = "GST"
    BASE_PATH = ""
    SENSITIVE_INFO = ("x-api-key",)

    def __init__(self, *args, **kwargs):
        self.settings = frappe.get_cached_doc("GST Settings")
        if not is_api_enabled(self.settings):
            frappe.throw(
                _("Please enable API in GST Settings to use the {0} API").format(
                    self.API_NAME
                )
            )

        self.sandbox_mode = self.settings.sandbox_mode
        self.default_headers = {
            "x-api-key": (
                (self.settings.api_secret and self.settings.get_password("api_secret"))
                or frappe.conf.ic_api_secret
            )
        }
        self.default_log_values = {}

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
                ).format(self.API_NAME),
                frappe.DoesNotExistError,
                title=_("Credentials Unavailable"),
            )

        self.username = row.username
        self.company = row.company
        self._fetch_credentials(row, require_password=require_password)

    def _fetch_credentials(self, row, require_password=True):
        self.password = row.get_password(raise_exception=require_password)

    def get_url(self, *parts):
        parts = list(parts)

        if self.BASE_PATH:
            parts.insert(0, self.BASE_PATH)

        if self.sandbox_mode:
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
                **self.default_headers,
                **(headers or {}),
            },
        )

        log_headers = request_args.headers.copy()

        log = frappe._dict(
            **self.default_log_values,
            url=request_args.url,
            data=request_args.params,
            request_headers=log_headers,
        )

        if method == "POST" and json:
            request_args.json = json

            json_data = json.copy()
            if not request_args.params:
                log.data = json_data
            else:
                log.data = {
                    "params": request_args.params,
                    "body": json_data,
                }

        response_json = None

        try:
            self.before_request(request_args)

            response = requests.request(method, **request_args)
            if api_request_id := response.headers.get("x-amzn-RequestId"):
                log.request_id = api_request_id

            try:
                response_json = response.json(object_hook=frappe._dict)
            except Exception:
                pass

            # Raise special error for certain HTTP codes
            self.handle_http_code(response.status_code, response_json)

            # Raise HTTPError for other HTTP codes
            response.raise_for_status()

            # Expect all successful responses to be JSON
            if not response_json:
                if "tar.gz" in request_args.url:
                    response_json = response.content

                else:
                    frappe.throw(
                        _("Error parsing response: {0}").format(response.content)
                    )

            response_json = self.process_response(response_json)
            return response_json.get("result", response_json)

        except Exception as e:
            log.error = str(e)
            raise e

        finally:
            log.output = response_json.copy()
            self.mask_sensitive_info(log)

            enqueue_integration_request(**log)

            if self.sandbox_mode and not frappe.flags.ic_sandbox_message_shown:
                frappe.msgprint(
                    _("GST API request was made in Sandbox Mode"),
                    alert=True,
                )
                frappe.flags.ic_sandbox_message_shown = True

    def before_request(self, request_args):
        return

    def process_response(self, response):
        self.handle_error_response(response)
        self.response = response
        return response

    def handle_error_response(self, response_json):
        # All error responses have a success key set to false
        success_value = response_json.get("success", True)
        if isinstance(success_value, str):
            success_value = sbool(success_value)

        if not success_value:
            self.handle_server_error(response_json)

        if not success_value and not self.is_ignored_error(response_json):
            frappe.throw(
                response_json.get("message")
                # Fallback to response body if message is not present
                or frappe.as_json(response_json, indent=4),
                title=_("API Request Failed"),
            )

    def handle_server_error(self, response_json):
        error_message_list = [
            "GSPGSTDOWN",
            "GSPERR300",
            "Connection reset",
            "No route to host",
        ]

        for error in error_message_list:
            if error in response_json.get("message"):
                raise GSPServerError

    def is_ignored_error(self, response_json):
        # Override in subclass, return truthy value to stop frappe.throw
        pass

    def handle_http_code(self, status_code, response_json):
        # TODO: add link to account page / support email

        # GSP connectivity issues
        if status_code == 401 or (
            status_code == 403
            and response_json
            and response_json.get("error") == "access_denied"
        ):
            frappe.throw(
                _("Error establishing connection to GSP. Please contact {0}.").format(
                    _("your Service Provider")
                    if frappe.conf.ic_api_key
                    else _("India Compliance API Support")
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

        if status_code == 504:
            raise GatewayTimeoutError

    def generate_request_id(self, length=12):
        return frappe.generate_hash(length=length)

    def mask_sensitive_info(self, log):
        for key in self.SENSITIVE_INFO:
            if key in log.request_headers:
                log.request_headers[key] = "*****"

            if key in log.output:
                log.output[key] = "*****"

            if not log.data:
                return

            if key in log.get("data", {}):
                log.data[key] = "*****"

            if key in log.get("data", {}).get("body", {}):
                log.data["body"][key] = "*****"


def get_public_ip():
    return requests.get("https://api.ipify.org").text


def check_scheduler_status():
    """
    Throw an error if scheduler is disabled
    """

    if frappe.flags.in_test or frappe.conf.developer_mode:
        return

    if frappe.utils.scheduler.is_scheduler_disabled():
        frappe.throw(
            _(
                "The Scheduler is currently disabled, which needs to be enabled to use e-Invoicing and e-Waybill features. "
                "Please get in touch with your server administrator to resolve this issue.<br><br>"
                "For more information, refer to the following documentation: {0}"
            ).format(
                """
                <a href="https://frappeframework.com/docs/user/en/bench/resources/bench-commands-cheatsheet#scheduler" target="_blank">
                    Frappe Scheduler Documentation
                </a>
                """
            )
        )
