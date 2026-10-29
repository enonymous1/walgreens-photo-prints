"""Errors raised by the Walgreens Photo Prints client."""


class ConfigError(ValueError):
    """Configuration is missing or invalid (credentials, base URL, timeout)."""


class WalgreensApiError(RuntimeError):
    """The Walgreens API returned an error, or the request failed.

    Attributes:
        status_code: HTTP status code, when the request reached the server.
        err_code: API-level ``err`` / ``errCode`` value, when present.
        err_desc: API-level ``errDesc`` text, when present.
        retry_after: Seconds from a ``Retry-After`` header on a 429, if any.
        throttled: True when the failure was a 429 rate-limit response.
            Data collected while throttled is degraded, never a measurement.
    """

    def __init__(
        self,
        message,
        *,
        status_code=None,
        err_code=None,
        err_desc=None,
        retry_after=None,
        throttled=False,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.err_code = err_code
        self.err_desc = err_desc
        self.retry_after = retry_after
        self.throttled = throttled
