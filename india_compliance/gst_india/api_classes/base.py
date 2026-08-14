import copy
from base64 import b64decode
from typing import ClassVar
from urllib.parse import quote, urljoin

import frappe
import requests
from frappe import _
from frappe.utils import sbool
from frappe.utils.scheduler import is_scheduler_disabled

from india_compliance.exceptions import (
    GatewayTimeoutError,
    GSPLimitExceededError,
    GSPServerError,
)
from india_compliance.gst_india.utils import is_api_enabled
from india_compliance.gst_india.utils.api import enqueue_integration_request

BASE_URL = "https://asp.resilient.tech"
DEFAULT_SUPPORT_EMAIL = "api-support@indiacompliance.app"

SERVER_DOWN_CACHE_KEY = "gst_server_down"
SERVER_DOWN_CACHE_TIMEOUT = 120


class BaseAPI:
    API_NAME = "GST"
    BASE_PATH = ""
    PLACEHOLDER = "*****"

    # (connect, read) secs. no read limit, downloads can be slow.
    REQUEST_TIMEOUT = (10, None)

    # skip request if server was down in the last 2 mins
    FAIL_FAST_IF_SERVER_DOWN = False

    DEFAULT_MASK_MAP: ClassVar[dict] = {
        "headers": [
            "x-api-key",
            "auth-token",
            "auth_token",
            "AuthToken",
            "password",
            "Password",
        ],
        "output": [
            "auth-token",
            "auth_token",
            "AuthToken",
            "sek",
            "Sek",
            "rek",
            "Rek",
        ],
        "data": ["app_key", "AppKey", "password", "Password"],
        "body": ["app_key", "AppKey", "password", "Password"],
    }

    def __init__(self, *args, **kwargs):
        self.settings = frappe.get_cached_doc("GST Settings")
        if not is_api_enabled(self.settings):
            frappe.throw(_("Please enable API in GST Settings to use the {0} API").format(self.API_NAME))

        self.company_gstin = None
        self.auth_strategy = None
        self.sandbox_mode = self.settings.sandbox_mode
        self.default_headers = {
            "x-api-key": (
                (self.settings.api_secret and self.settings.get_password("api_secret"))
                or frappe.conf.ic_api_secret
            )
        }
        self.default_log_values = {}
        self.support_email = None

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
                    "Please set the relevant credentials for GSTIN {0} in GST Settings to use the {1} API"
                ).format(gstin, self.API_NAME),
                frappe.DoesNotExistError,
                title=_("Credentials Unavailable"),
            )

        self.username = row.username
        self.company = row.company
        self.app_key = row.app_key or self.generate_app_key(service)
        self._fetch_credentials(row, require_password=require_password)

    def _fetch_credentials(self, row, require_password=True):
        self.password = row.get_password(raise_exception=require_password)
        self.session_key = b64decode(row.session_key or "")
        self.session_expiry = row.session_expiry
        self.auth_token = row.auth_token
        self.session_ip = row.session_ip

    def get_url(self, *parts):
        parts = list(parts)

        if parts and parts[0].startswith("https"):
            return parts[0]

        if self.BASE_PATH:
            parts.insert(0, self.BASE_PATH)

        if self.sandbox_mode:
            parts.insert(0, "test")

        return urljoin(BASE_URL, "/".join(part.strip("/") for part in parts))

    def get(self, *args, **kwargs):
        return self._make_request("GET", *args, **kwargs)

    def post(self, *args, **kwargs):
        return self._make_request("POST", *args, **kwargs)

    def put(self, *args, **kwargs):
        return self._make_request("PUT", *args, **kwargs)

    def _make_request(
        self,
        method,
        endpoint="",
        params=None,
        headers=None,
        json=None,
    ):
        method = method.upper()
        if method not in ("GET", "POST", "PUT"):
            frappe.throw(_("Invalid method {0}").format(method))

        self.check_server_status()

        request_args = frappe._dict(
            url=self.get_url(endpoint),
            params=params,
            headers={
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

        if method in ["POST", "PUT"] and json:
            request_args.json = json

            json_data = json.copy()
            if not request_args.params:
                log.data = json_data
            else:
                log.data = {
                    "params": request_args.params,
                    "body": json_data,
                }

        response = None
        response_json = None

        try:
            self.before_request(request_args)

            # raise known errors, so auto-retry kicks in
            try:
                response = requests.request(method, timeout=self.REQUEST_TIMEOUT, **request_args)
            except requests.exceptions.Timeout as e:
                raise GatewayTimeoutError(str(e)) from e
            except requests.exceptions.ConnectionError as e:
                raise GSPServerError(str(e)) from e

            if api_request_id := response.headers.get("x-amzn-RequestId"):
                self.request_id = api_request_id
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
                    frappe.throw(_("Error parsing response: {0}").format(response.content))

            response_json = self.process_response(response_json)

            if response_json.get("error_type") == "invalid_public_key":
                return self._make_request(method, endpoint, params, headers, json)

            return response_json.get("result", response_json)

        except Exception as e:
            log.error = str(e)
            self.mark_server_down(e)
            raise e

        finally:
            if response_json:
                log.output = response_json.copy()
            elif response:
                log.output = {
                    "status_code": response.status_code,
                    "content": response.text,
                }

            self.mask_sensitive_info(log)

            enqueue_integration_request(**log)

            if self.sandbox_mode and not frappe.flags.ic_sandbox_message_shown:
                frappe.msgprint(
                    _("GST API request was made in Sandbox Mode"),
                    alert=True,
                )
                frappe.flags.ic_sandbox_message_shown = True

    def before_request(self, request_args):
        if getattr(self, "auth_strategy", None):
            self.auth_strategy.prepare_request(request_args)

    def process_response(self, response):
        self.handle_error_response(response)

        if getattr(self, "auth_strategy", None):
            response = self.auth_strategy.process_response(response)

        self.response = response
        return response

    def handle_error_response(self, response_json):
        # All error responses have a success key set to false
        success_value = response_json.get("success", True)
        if isinstance(success_value, str):
            success_value = sbool(success_value)

        if not success_value:
            self.handle_server_error([response_json.get("message")])

        if not success_value and not self.is_ignored_error(response_json):
            frappe.throw(
                response_json.get("message")
                # Fallback to response body if message is not present
                or frappe.as_json(response_json, indent=4),
                title=_("API Request Failed"),
            )

    ERROR_MESSAGES: ClassVar[dict] = {
        GSPServerError: (
            "GSPGSTDOWN",
            "GSPERR300",
            "Connection reset",
            "No route to host",
        ),
        GSPLimitExceededError: ("GEN5005",),
    }

    def handle_server_error(self, error_messages):
        for exception, error_message_list in self.ERROR_MESSAGES.items():
            for error_pattern in error_message_list:
                if any(error_pattern in msg for msg in error_messages if msg):
                    frappe.throw(
                        msg=exception.message,
                        exc=exception,
                        title=exception.title,
                    )

    def check_server_status(self):
        if not (self.FAIL_FAST_IF_SERVER_DOWN and frappe.cache.get_value(SERVER_DOWN_CACHE_KEY)):
            return

        frappe.throw(
            msg=GSPServerError.message,
            exc=GSPServerError,
            title=GSPServerError.title,
        )

    def mark_server_down(self, error):
        if not self.FAIL_FAST_IF_SERVER_DOWN:
            return

        # limit exceeded is not an outage
        if not isinstance(error, GSPServerError) or isinstance(error, GSPLimitExceededError):
            return

        frappe.cache.set_value(SERVER_DOWN_CACHE_KEY, True, expires_in_sec=SERVER_DOWN_CACHE_TIMEOUT)

    def is_ignored_error(self, response_json):
        # Override in subclass, return truthy value to stop frappe.throw
        pass

    def handle_http_code(self, status_code, response_json):
        # GSP connectivity issues
        if status_code == 401 or (
            status_code == 403 and response_json and response_json.get("error") == "access_denied"
        ):
            frappe.throw(
                _("Error establishing connection to GSP.<br><br>Please contact support at {0}").format(
                    frappe.bold(self.get_support_email_link(error=response_json))
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

    def get_support_email_link(self, subject="Error establishing connection to GSP", error=None):
        email = self.support_email or DEFAULT_SUPPORT_EMAIL

        if company := getattr(self, "company", None):
            subject = f"{subject} - {company}"

        if error:
            body = f"Hello India Compliance Team,\n\n\n{error}\n"
        else:
            body = (
                "Hello India Compliance Team,\n\n\n// Please describe the issue and paste the error here...\n"
            )

        # &amp; keeps the href valid HTML.
        mailto = f"mailto:{email}?subject={quote(subject)}&amp;body={quote(body)}"
        return f'<a href="{mailto}">{email}</a>'

    def generate_request_id(self, length=12):
        return f"IC{frappe.generate_hash(length=length - 2)}".upper()

    def mask_sensitive_info(self, log):
        request_headers = log.request_headers
        output = log.output
        data = log.data
        request_body = data and data.get("body")

        # Define specific locations where each type of sensitive info should be masked
        sensitive_info_mapping = self._get_sensitive_info_mapping()

        self._mask_sensitive_info(request_headers, sensitive_info_mapping.get("headers"))

        self._mask_sensitive_info(output, sensitive_info_mapping.get("output"))
        self._mask_sensitive_info(data, sensitive_info_mapping.get("data"))
        self._mask_sensitive_info(request_body, sensitive_info_mapping.get("body"))

    def _get_sensitive_info_mapping(self):
        default_mapping = copy.deepcopy(self.DEFAULT_MASK_MAP)

        # Get subclass-specific overrides
        overrides = self._get_sensitive_info_overrides()

        # Merge overrides with default mapping
        if overrides:
            default_mapping.update(overrides)

        return default_mapping

    def _get_sensitive_info_overrides(self):
        return {}

    def _mask_sensitive_info(self, target, sensitive_keys):
        if not (target and sensitive_keys):
            return

        for key in sensitive_keys:
            if key in target:
                target[key] = self.PLACEHOLDER

    def generate_app_key(self, service):
        app_key = frappe.generate_hash(length=32)

        frappe.db.set_value(
            "GST Credential",
            {
                "gstin": self.company_gstin,
                "username": self.username,
                "service": service,
            },
            {"app_key": app_key},
        )

        return app_key


def check_scheduler_status():
    """
    Throw an error if scheduler is disabled
    """

    if frappe.flags.in_test or frappe.conf.developer_mode:
        return

    if is_scheduler_disabled():
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


def change_base_path(new_base_path):
    """
    Decorator to change the base path of the API class for wrapped method only.
    """

    def decorator(func):
        def wrapper(self, *args, **kwargs):
            original_base_path = self.BASE_PATH
            self.BASE_PATH = new_base_path
            try:
                return func(self, *args, **kwargs)
            finally:
                self.BASE_PATH = original_base_path

        return wrapper

    return decorator
