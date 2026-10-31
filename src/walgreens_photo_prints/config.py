"""Configuration for the Walgreens Photo Prints client.

Credentials are never hardcoded. They come from the environment (or a
``.env`` file), and the API key is excluded from ``repr``.
"""

import os
from dataclasses import dataclass, field
from urllib.parse import urlparse

from .errors import ConfigError

SANDBOX_BASE_URL = "https://services-qa.walgreens.com"
PRODUCTION_BASE_URL = "https://services.walgreens.com"
DEFAULT_TIMEOUT = 30.0


@dataclass(frozen=True)
class Config:
    """Client configuration.

    ``api_key`` and ``aff_id`` are required. ``app_ver`` and ``dev_inf``
    are optional for the credentials and products endpoints, and required
    by the API for coupon, store, and submit calls; the client raises a
    clear error when a call needs them and neither the config nor the
    call arguments supply them.

    The default base URL is the sandbox host on purpose: a missing
    ``WALGREENS_BASE_URL`` must never accidentally place a production
    order. Production requires an explicit opt-in.
    """

    api_key: str = field(repr=False)
    aff_id: str
    base_url: str = SANDBOX_BASE_URL
    platform: str = "ios"
    app_ver: str | None = None
    dev_inf: str | None = None
    timeout: float = DEFAULT_TIMEOUT

    def __post_init__(self):
        if not self.api_key or not self.api_key.strip():
            raise ConfigError("WALGREENS_API_KEY is required and must not be empty.")
        if not self.aff_id or not self.aff_id.strip():
            raise ConfigError("WALGREENS_AFF_ID is required and must not be empty.")
        base_url = self.base_url.strip().rstrip("/")
        if not base_url.startswith("https://"):
            raise ConfigError(f"WALGREENS_BASE_URL must start with https://, got {base_url!r}.")
        object.__setattr__(self, "api_key", self.api_key.strip())
        object.__setattr__(self, "aff_id", self.aff_id.strip())
        object.__setattr__(self, "base_url", base_url)
        if not self.platform or not self.platform.strip():
            raise ConfigError("Platform must not be empty.")
        object.__setattr__(self, "platform", self.platform.strip())
        if self.app_ver is not None:
            object.__setattr__(self, "app_ver", self.app_ver.strip() or None)
        if self.dev_inf is not None:
            object.__setattr__(self, "dev_inf", self.dev_inf.strip() or None)
        try:
            timeout_ok = self.timeout is not None and self.timeout > 0
        except TypeError:
            timeout_ok = False
        if not timeout_ok:
            raise ConfigError(f"Timeout must be a positive number, got {self.timeout!r}.")

    @property
    def is_sandbox(self):
        """True when the base URL host is the QA/sandbox host."""
        return urlparse(self.base_url).hostname == "services-qa.walgreens.com"

    @classmethod
    def from_env(cls, env=None, *, env_file=None):
        """Build a Config from environment variables.

        Precedence, highest first: the ``env`` mapping (or
        ``os.environ`` when ``env`` is None), then the dotenv file.
        The dotenv file is parsed without mutating ``os.environ``,
        so passing an explicit ``env`` mapping sees the file values
        too. When ``env_file`` is None, a ``.env`` file in the
        working directory is used when present.
        """
        file_values = {}
        dotenv_path = env_file
        if dotenv_path is None and os.path.exists(".env"):
            dotenv_path = ".env"
        if dotenv_path is not None:
            file_values = _dotenv_values(dotenv_path)
        values = os.environ if env is None else env
        merged = {**file_values, **values}
        api_key = merged.get("WALGREENS_API_KEY", "") or ""
        aff_id = merged.get("WALGREENS_AFF_ID", "") or ""
        base_url = merged.get("WALGREENS_BASE_URL") or SANDBOX_BASE_URL
        platform = merged.get("WALGREENS_PLATFORM") or "ios"
        app_ver = merged.get("WALGREENS_APP_VER") or None
        dev_inf = merged.get("WALGREENS_DEV_INF") or None
        timeout_raw = merged.get("WALGREENS_TIMEOUT")
        try:
            timeout = float(timeout_raw) if timeout_raw else DEFAULT_TIMEOUT
        except ValueError:
            raise ConfigError(f"WALGREENS_TIMEOUT must be a number, got {timeout_raw!r}.") from None
        return cls(
            api_key=api_key,
            aff_id=aff_id,
            base_url=base_url,
            platform=platform,
            app_ver=app_ver,
            dev_inf=dev_inf,
            timeout=timeout,
        )


def _dotenv_values(path):
    """Parse a dotenv file into a dict, without touching ``os.environ``."""
    try:
        from dotenv import dotenv_values
    except ImportError:  # pragma: no cover - python-dotenv is a dependency
        return {}
    values = dotenv_values(path)
    return {key: value for key, value in values.items() if value is not None}
