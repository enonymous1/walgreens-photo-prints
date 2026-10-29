"""Configuration for the Walgreens Photo Prints client.

Credentials are never hardcoded. They come from the environment (or a
``.env`` file), and the API key is excluded from ``repr``.
"""

import os
from dataclasses import dataclass, field

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
        if self.timeout <= 0:
            raise ConfigError(f"Timeout must be positive, got {self.timeout!r}.")

    @property
    def is_sandbox(self):
        """True when the base URL is the QA/sandbox host."""
        return "services-qa.walgreens.com" in self.base_url

    @classmethod
    def from_env(cls, env=None, *, env_file=None):
        """Build a Config from environment variables.

        ``env`` defaults to ``os.environ``. When ``env_file`` is given, or
        when a ``.env`` file exists in the working directory, values from
        it fill in variables that are not already set in the environment;
        real environment variables always win.
        """
        if env_file is not None:
            _load_dotenv(env_file)
        elif os.path.exists(".env"):
            _load_dotenv(".env")
        values = os.environ if env is None else env
        api_key = values.get("WALGREENS_API_KEY", "")
        aff_id = values.get("WALGREENS_AFF_ID", "")
        base_url = values.get("WALGREENS_BASE_URL") or SANDBOX_BASE_URL
        platform = values.get("WALGREENS_PLATFORM") or "ios"
        app_ver = values.get("WALGREENS_APP_VER") or None
        dev_inf = values.get("WALGREENS_DEV_INF") or None
        timeout_raw = values.get("WALGREENS_TIMEOUT")
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


def _load_dotenv(path):
    """Load a dotenv file without overwriting existing environment values."""
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - python-dotenv is a dependency
        return
    load_dotenv(path, override=False)
