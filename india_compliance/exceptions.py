class GSPServerError(Exception):
    def __init__(self, message="GSP/GST server is down", *args, **kwargs):
        super().__init__(message, *args, **kwargs)


class GatewayTimeoutError(GSPServerError):
    def __init__(self, message="The server took too long to respond", *args, **kwargs):
        super().__init__(message, *args, **kwargs)
