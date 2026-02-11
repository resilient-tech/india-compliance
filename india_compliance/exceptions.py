from frappe import ValidationError


class GSPServerError(ValidationError):
    message = "GSP/GST server is down"
    title = "GSP/GST Server Error"


class GSPLimitExceededError(GSPServerError):
    message = "GSP/GST account limit exceeded"
    http_status_code = 429


class GatewayTimeoutError(GSPServerError):
    message = "The server took too long to respond"
    http_status_code = 504


class OTPRequestedError(Exception):
    def __init__(self, message="OTP has been requested", *args, **kwargs):
        self.response = kwargs.pop("response", None)
        super().__init__(message, *args, **kwargs)


class InvalidOTPError(Exception):
    def __init__(self, message="Invalid OTP", *args, **kwargs):
        self.response = kwargs.pop("response", None)
        super().__init__(message, *args, **kwargs)


class InvalidAuthTokenError(Exception):
    def __init__(self, message="Invalid Auth Token", *args, **kwargs):
        super().__init__(message, *args, **kwargs)


class NotApplicableError(ValidationError):
    """
    Raised when e-Invoice/e-Waybill is not applicable for the document.
    """

    pass


class AlreadyGeneratedError(ValidationError):
    """
    Raised when e-Invoice/e-Waybill has already been generated for the document.
    """

    pass
