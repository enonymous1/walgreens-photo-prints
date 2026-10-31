"""HTTP client for the Walgreens Native Photo Prints API v3.

Every method sends one POST with a JSON body, a timeout, and an
explicit error check. Nothing is requested on import, and nothing is
requested twice: callers fetch credentials once and reuse them.

Error handling: a non-2xx HTTP status, a non-JSON body, a non-object
JSON body, or an API-level error (``err`` / ``errCode`` non-empty, or
``status`` of ``error`` / ``failure``) all raise ``WalgreensApiError``.
A 429 raises with ``throttled=True`` and the ``Retry-After`` value when
the server sent one; the caller must wait and re-run, and must not
treat a throttled collection as a measurement.

Rate limits stated in the API reference (requests per minute):
creds 300, products 300, coupon 100, store 300, submit 300, status 300.
This client does not retry or pace; callers that loop must pace
themselves to those limits.

There is deliberately no automatic retry. ``submit_order`` is not
idempotent: retrying it after a timeout could place the order twice.
The idempotent endpoints (credentials, products, stores, status,
coupon validation) are safe for a caller to retry; submit is not, so
retry policy stays with the caller, not the client.
"""

import logging

import requests

from ._version import __version__
from .config import Config
from .errors import ConfigError, WalgreensApiError
from .models import (
    CouponResult,
    ImageDetail,
    OrderProduct,
    OrderSubmission,
    ProductQty,
    UploadCredentials,
    parse_order_statuses,
    parse_products,
    parse_stores,
)
from .transport import RequestsTransport

logger = logging.getLogger(__name__)

API_VERSION = "v3"

ENDPOINTS = {
    "creds": f"/api/photo/creds/{API_VERSION}",
    "products": f"/api/photo/products/{API_VERSION}",
    "coupon": f"/api/photo/order/coupon/{API_VERSION}",
    "stores": f"/api/photo/store/{API_VERSION}",
    "submit": f"/api/photo/order/submit/{API_VERSION}",
    "status": f"/api/photo/order/status/{API_VERSION}",
}

# Documented limits only: this client does not enforce them.
# Callers that loop must pace themselves to these values.
DOCUMENTED_RATE_LIMITS_PER_MINUTE = {
    "creds": 300,
    "products": 300,
    "coupon": 100,
    "store": 300,
    "submit": 300,
    "status": 300,
}

# Backwards-compatible alias for the pre-1.2.0 name.
RATE_LIMITS_PER_MINUTE = DOCUMENTED_RATE_LIMITS_PER_MINUTE

MAX_DISTINCT_IMAGES = 200
MAX_QTY_PER_IMAGE = 20


class WalgreensClient:
    """A session-bound client for one Walgreens affiliate account.

    ``session`` (a ``requests``-compatible session) is kept for
    backwards compatibility; ``transport`` takes precedence when
    both are given. A transport/session passed in belongs to the
    caller and is never closed by this client; one created here
    is closed by ``close()`` / context-manager exit.
    """

    def __init__(self, config, session=None, transport=None):
        if isinstance(config, Config):
            self.config = config
        else:  # pragma: no cover - defensive, tests use Config
            raise TypeError("config must be a Config instance")
        if transport is not None:
            self._transport = transport
        elif session is not None:
            self._transport = RequestsTransport(session)
        else:
            self._transport = RequestsTransport()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def close(self):
        self._transport.close()

    # -- internals -----------------------------------------------------

    def _post(self, path, payload):
        """Send one JSON POST and return the response object.

        Raises ``WalgreensApiError`` for transport failures, HTTP
        errors (including the response body, truncated, so the API's
        own error text is not lost), non-JSON or non-object bodies,
        and API-level errors. A 429 additionally sets
        ``throttled=True``. Payloads are never logged: they contain
        the API key.
        """
        url = self.config.base_url + path
        headers = {
            "Content-Type": "application/json",
            "User-Agent": f"walgreens-photo-prints/{__version__}",
        }
        try:
            response = self._transport.post(
                url, headers=headers, json=payload, timeout=self.config.timeout
            )
        except requests.RequestException as exc:
            raise WalgreensApiError(f"Request to {path} failed: {exc}") from exc
        logger.debug("POST %s -> HTTP %s", path, response.status_code)
        if response.status_code == 429:
            retry_after = _retry_after_seconds(response)
            raise WalgreensApiError(
                "Walgreens API rate limit reached (HTTP 429). "
                "Wait out the limit and re-run; do not treat a throttled "
                "result as a measurement.",
                status_code=429,
                retry_after=retry_after,
                throttled=True,
            )
        if not 200 <= response.status_code < 300:
            body = (getattr(response, "text", "") or "")[:200]
            raise WalgreensApiError(
                f"Walgreens API returned HTTP {response.status_code} for {path}. {body}",
                status_code=response.status_code,
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise WalgreensApiError(
                f"Walgreens API returned a non-JSON response for {path}."
            ) from exc
        if not isinstance(data, dict):
            raise WalgreensApiError(
                f"Walgreens API returned a non-object JSON response for {path}."
            )
        _raise_for_api_error(data, path)
        return data

    def _base_payload(self, app_ver=None, dev_inf=None, *, require_app_and_device=False):
        """Base payload: credentials plus optional app/device fields.

        When ``require_app_and_device`` is set, both fields must
        resolve (from arguments or config) or ``ConfigError`` is
        raised before any request is sent.
        """
        payload = {"apiKey": self.config.api_key, "affId": self.config.aff_id}
        resolved_ver = app_ver if app_ver is not None else self.config.app_ver
        resolved_inf = dev_inf if dev_inf is not None else self.config.dev_inf
        if require_app_and_device and (resolved_ver is None or resolved_inf is None):
            raise ConfigError(
                "This endpoint requires appVer and devInf. Set "
                "WALGREENS_APP_VER / WALGREENS_DEV_INF or pass them explicitly."
            )
        if resolved_ver is not None:
            payload["appVer"] = resolved_ver
        if resolved_inf is not None:
            payload["devInf"] = resolved_inf
        return payload

    # -- endpoints ------------------------------------------------------

    def fetch_upload_credentials(self, *, platform=None, app_ver=None, dev_inf=None):
        """Fetch upload credentials (``/api/photo/creds/v3``)."""
        payload = self._base_payload(app_ver, dev_inf)
        payload["platform"] = platform or self.config.platform
        payload["transaction"] = "photocheckoutv2"
        data = self._post(ENDPOINTS["creds"], payload)
        return UploadCredentials.from_dict(data)

    def list_products(self, *, product_group_id=None, app_ver=None, dev_inf=None):
        """List products and prices (``/api/photo/products/v3``).

        Call this every time products or prices are shown: the
        reference states prices and products can change at any time.
        Returns products in the order the API returned them.
        """
        payload = self._base_payload(app_ver, dev_inf)
        if product_group_id is not None:
            payload["productGroupId"] = product_group_id
        payload["act"] = "getphotoprods"
        data = self._post(ENDPOINTS["products"], payload)
        return parse_products(data)

    def validate_coupon(self, coupon_code, product_details, *, app_ver=None, dev_inf=None):
        """Validate a coupon (``/api/photo/order/coupon/v3``).

        ``product_details`` is a list of ``{"productId": ..., "qty": ...}``
        mappings. Only add the coupon to a submit request after a
        successful validation.
        """
        payload = self._base_payload(app_ver, dev_inf, require_app_and_device=True)
        payload["couponCode"] = coupon_code
        payload["act"] = "getdiscount"
        payload["productDetails"] = [
            _product_qty_payload(d)
            for d in _require_non_empty_list(product_details, "productDetails")
        ]
        data = self._post(ENDPOINTS["coupon"], payload)
        return CouponResult.from_dict(data)

    def find_stores(self, latitude, longitude, product_details, *, app_ver=None, dev_inf=None):
        """Find photo stores near a location (``/api/photo/store/v3``).

        ``latitude``/``longitude`` may be strings or numbers; they are
        validated to -90..90 / -180..180 and sent as strings, as in
        the API examples. Returns stores in the order the API returned
        them. A store whose ``promise_time`` is
        ``01-01-3000 00:00 AM`` is in the API's no-promise-time state
        (see ``PhotoStore.is_no_promise_time``).
        """
        payload = self._base_payload(app_ver, dev_inf, require_app_and_device=True)
        latitude, longitude = _validate_lat_lon(latitude, longitude)
        payload["latitude"] = latitude
        payload["longitude"] = longitude
        payload["act"] = "photoStores"
        payload["productDetails"] = [
            _product_qty_payload(d)
            for d in _require_non_empty_list(product_details, "productDetails")
        ]
        data = self._post(ENDPOINTS["stores"], payload)
        return parse_stores(data)

    def submit_order(
        self,
        *,
        first_name,
        last_name,
        phone,
        email,
        store_num,
        promise_time,
        product_details,
        coupon_code=None,
        publisher_id=None,
        aff_notes=None,
        app_ver=None,
        dev_inf=None,
        terms_accepted=False,
    ):
        """Submit a photo order (``/api/photo/order/submit/v3``).

        This places a real order. ``terms_accepted`` must be True: the
        API requires the customer to take an action on a terms element
        for every order, so the caller must have collected that action
        before calling this method.

        Client-side limits from the API reference are enforced before
        any request is sent: at most 200 distinct images, and at most
        20 prints per image URL for standard prints. The post-coupon
        price limit (under $998) cannot be checked here; validate the
        coupon and check the total before submitting.
        """
        if not terms_accepted:
            raise ValueError(
                "Refusing to submit: terms_accepted must be True. The customer "
                "must take an action on the terms element for every order."
            )
        payload = self.build_submit_payload(
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            email=email,
            store_num=store_num,
            promise_time=promise_time,
            product_details=product_details,
            coupon_code=coupon_code,
            publisher_id=publisher_id,
            aff_notes=aff_notes,
            app_ver=app_ver,
            dev_inf=dev_inf,
        )
        data = self._post(ENDPOINTS["submit"], payload)
        return OrderSubmission.from_dict(data)

    def build_submit_payload(
        self,
        *,
        first_name,
        last_name,
        phone,
        email,
        store_num,
        promise_time,
        product_details,
        coupon_code=None,
        publisher_id=None,
        aff_notes=None,
        app_ver=None,
        dev_inf=None,
    ):
        """Build (and validate) a submit payload without sending it.

        The returned payload contains the API key; callers that print
        it must redact ``apiKey`` first. Validation here is the same
        whether the caller is the library or the CLI: required
        customer/store fields must be non-empty, at least one product
        with at least one image is required, quantities are integers
        in 1..20, and distinct image URLs across the order must not
        exceed the API limit.
        """
        _require_non_empty(first_name, "first_name")
        _require_non_empty(last_name, "last_name")
        _require_non_empty(phone, "phone")
        _require_non_empty(email, "email")
        _require_non_empty(store_num, "store_num")
        _require_non_empty(promise_time, "promise_time")
        products = [
            _coerce_order_product(d)
            for d in _require_non_empty_list(product_details, "product_details")
        ]
        for product in products:
            if not product.image_details:
                raise ValueError(f"Order product {product.product_id!r} needs at least one image.")
        distinct_urls = set()
        for product in products:
            distinct_urls.update(product.distinct_image_urls())
        if len(distinct_urls) > MAX_DISTINCT_IMAGES:
            raise ValueError(
                f"Order has {len(distinct_urls)} distinct images; "
                f"the API allows at most {MAX_DISTINCT_IMAGES}."
            )
        for product in products:
            for image in product.image_details:
                _validate_qty(image.qty)
        payload = self._base_payload(app_ver, dev_inf)
        if publisher_id is not None:
            payload["publisherId"] = publisher_id
        payload["firstName"] = first_name
        payload["lastName"] = last_name
        payload["phone"] = phone
        payload["email"] = email
        if coupon_code is not None:
            payload["couponCode"] = coupon_code
        payload["storeNum"] = str(store_num)
        payload["promiseTime"] = promise_time
        if aff_notes is not None:
            payload["affNotes"] = aff_notes
        payload["act"] = "submitphotoorder"
        payload["productDetails"] = [p.to_payload() for p in products]
        return payload

    def get_order_status(self, order_ids, *, app_ver=None, dev_inf=None):
        """Fetch order statuses (``/api/photo/order/status/v3``).

        ``order_ids`` is a non-empty list of vendor order IDs. Returns
        statuses in the order the API returned them.
        """
        order_ids = list(order_ids)
        if not order_ids:
            raise ValueError("At least one vendor order ID is required.")
        payload = self._base_payload(app_ver, dev_inf)
        payload["orders"] = [str(o) for o in order_ids]
        payload["act"] = "orderstatus"
        data = self._post(ENDPOINTS["status"], payload)
        return parse_order_statuses(data)


def _require_non_empty(value, name):
    if value is None or str(value).strip() == "":
        raise ValueError(f"{name} must not be empty.")
    return str(value)


def _require_non_empty_list(value, name):
    items = list(value) if value is not None else []
    if not items:
        raise ValueError(f"{name} must contain at least one entry.")
    return items


def _validate_qty(value):
    """Validate a print quantity: an integer in 1..MAX_QTY_PER_IMAGE.

    Bools and floats are rejected outright so ``1.9`` is never
    silently truncated to ``1``, and ``0``/negatives fail here
    instead of at the API.
    """
    if isinstance(value, bool):
        raise ValueError(f"Image qty must be an integer, got {value!r}.")
    if isinstance(value, int):
        qty = value
    elif isinstance(value, str) and value.strip().isdigit():
        qty = int(value.strip())
    else:
        raise ValueError(f"Image qty must be an integer, got {value!r}.")
    if not 1 <= qty <= MAX_QTY_PER_IMAGE:
        raise ValueError(f"Image qty {qty} is outside the API range 1..{MAX_QTY_PER_IMAGE}.")
    return qty


def _validate_lat_lon(latitude, longitude):
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        raise ValueError(
            f"Latitude/longitude must be numbers, got {latitude!r}, {longitude!r}."
        ) from None
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError(f"Latitude/longitude out of range: {lat}, {lon}.")
    return str(lat), str(lon)


def _product_qty_payload(detail):
    """Normalise a coupon/store product entry to its payload.

    Accepts a ``ProductQty`` (preferred), a dict, or an object
    with ``product_id``/``qty`` attributes (kept for backwards
    compatibility with the pre-1.2.0 duck-typed input).
    """
    if isinstance(detail, ProductQty):
        return detail.to_payload()
    if isinstance(detail, dict):
        product_id = detail.get("productId")
        qty = detail.get("qty")
    else:
        product_id = getattr(detail, "product_id", None)
        qty = getattr(detail, "qty", None)
    if product_id is None or qty is None:
        raise ValueError(f"Each product detail needs a productId and a qty, got {detail!r}.")
    return {"productId": str(product_id), "qty": str(qty)}


def _coerce_order_product(detail):
    if isinstance(detail, OrderProduct):
        return detail
    if isinstance(detail, dict):
        images = [
            ImageDetail(url=str(i["url"]), qty=str(i.get("qty", "1")))
            for i in detail.get("imageDetails", [])
        ]
        return OrderProduct(
            product_id=str(detail["productId"]),
            image_details=images,
            multi_image_quantity=(
                str(detail["multiImageQuantity"])
                if detail.get("multiImageQuantity") is not None
                else None
            ),
        )
    raise TypeError(f"Order product must be an OrderProduct or dict, got {type(detail)}.")


def _raise_for_api_error(data, path):
    err = data.get("err") or data.get("errCode") or ""
    err_desc = data.get("errDesc") or ""
    status = str(data.get("status", "")).lower()
    if err or status in ("error", "failure"):
        raise WalgreensApiError(
            f"Walgreens API error for {path}: {err_desc or err or status}.",
            err_code=str(err) if err else None,
            err_desc=err_desc or None,
        )


def _retry_after_seconds(response):
    """Parse ``Retry-After`` as seconds, or as an HTTP date.

    Returns ``None`` when the header is absent or unparseable, so a
    malformed header never turns a rate-limit error into a crash.
    """
    raw = response.headers.get("Retry-After") if hasattr(response, "headers") else None
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        pass
    try:
        from datetime import datetime, timezone
        from email.utils import parsedate_to_datetime

        when = parsedate_to_datetime(str(raw))
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return max(0, int((when - datetime.now(timezone.utc)).total_seconds()))
    except (TypeError, ValueError, OverflowError):
        return None
