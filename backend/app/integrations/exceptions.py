class ProviderAPIError(Exception):
    def __init__(
        self,
        provider: str,
        status_code: int,
        message: str,
        retry_after: int | None = None,
    ):
        self.provider = provider
        self.status_code = status_code
        self.retry_after = retry_after
        super().__init__(f"{provider} API error ({status_code}): {message}")


class ProviderRateLimitError(ProviderAPIError):
    pass


class WebhookSignatureError(Exception):
    pass
