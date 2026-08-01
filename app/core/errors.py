class GatewayError(Exception):
    pass


class GatewayConfigError(GatewayError):
    pass


class UpstreamError(GatewayError):
    def __init__(self, provider: str, status_code: int, detail: str) -> None:
        self.provider = provider
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"{provider} returned {status_code}: {detail}")


class UpstreamProtocolError(GatewayError):
    def __init__(self, provider: str, detail: str) -> None:
        self.provider = provider
        self.detail = detail
        super().__init__(f"{provider} sent an unreadable response: {detail}")
