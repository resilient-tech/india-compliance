class GatewayTimeoutError(Exception):
    def __init__(self, message="Gateway Timeout Error", *args, **kwargs):
        self.message = message
        super().__init__(self.message, *args, **kwargs)
