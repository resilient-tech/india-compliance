class GSPServerError(Exception):
    def __init__(self, message="GSP/GST server is down", *args, **kwargs):
        super().__init__(message, *args, **kwargs)


class GatewayTimeoutError(GSPServerError):
    def __init__(self, message="The server took too long to respond", *args, **kwargs):
        super().__init__(message, *args, **kwargs)


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
