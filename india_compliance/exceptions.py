class GatewayTimeoutError(Exception):
    def __init__(self, message="The server took too long to respond", *args, **kwargs):
        self.message = message
        super().__init__(self.message, *args, **kwargs)
