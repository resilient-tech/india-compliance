from frappe import ValidationError


class GSPServerError(Exception):
    def __init__(self, message="GSP/GST server is down", *args, **kwargs):
        super().__init__(message, *args, **kwargs)


class GatewayTimeoutError(GSPServerError):
    def __init__(self, message="The server took too long to respond", *args, **kwargs):
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
