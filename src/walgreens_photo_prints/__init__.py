"""Walgreens Native Photo Prints API v3 client."""

from ._version import __version__

from .client import WalgreensClient
from .config import Config, ConfigError
from .errors import WalgreensApiError
from .models import (
    CouponResult,
    ImageDetail,
    OrderProduct,
    OrderStatusEntry,
    OrderSubmission,
    PhotoStore,
    Product,
    UploadCredentials,
)
from .upload import build_upload_url, upload_image, upload_image_for_credentials

__all__ = [
    "Config",
    "ConfigError",
    "CouponResult",
    "ImageDetail",
    "OrderProduct",
    "OrderStatusEntry",
    "OrderSubmission",
    "PhotoStore",
    "Product",
    "UploadCredentials",
    "WalgreensApiError",
    "WalgreensClient",
    "__version__",
    "build_upload_url",
    "upload_image",
    "upload_image_for_credentials",
]
