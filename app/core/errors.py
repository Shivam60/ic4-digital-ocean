from dataclasses import dataclass

TRANSIENT_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})


def is_transient_status(status_code: int) -> bool:
    return status_code in TRANSIENT_STATUS_CODES


class GatewayError(Exception):
    pass


class GatewayConfigError(GatewayError):
    pass


class AuthenticationError(GatewayError):
    pass


class AuthorizationError(GatewayError):
    def __init__(self, label: str, scope: str) -> None:
        self.label = label
        self.scope = scope
        super().__init__(f"key '{label}' is not permitted to use scope '{scope}'")


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


@dataclass(frozen=True)
class ProviderAttempt:
    provider: str
    status_code: int | None
    detail: str


class AllProvidersFailedError(GatewayError):
    def __init__(self, model: str, attempts: list[ProviderAttempt]) -> None:
        self.model = model
        self.attempts = attempts
        summary = ", ".join(
            f"{attempt.provider}={attempt.status_code or 'unreachable'}"
            for attempt in attempts
        )
        super().__init__(f"all providers failed for model '{model}': {summary}")
