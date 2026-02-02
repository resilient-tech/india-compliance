<<<<<<< HEAD
class GSPServerError(Exception):
    def __init__(self, message="GSP/GST server is down", *args, **kwargs):
        super().__init__(message, *args, **kwargs)
=======
from frappe import ValidationError


class GSPServerError(ValidationError):
    message = "GSP/GST server is down"
    title = "GSP/GST Server Error"


class GSPLimitExceededError(GSPServerError):
    message = "GSP/GST account limit exceeded"
    http_status_code = 429
>>>>>>> c9f457eb (Merge pull request #3918 from karm1000/e-invoice/handle-already-generated)


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
