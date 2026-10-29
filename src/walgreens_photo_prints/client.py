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
"""

import requests

from .config import Config
from .errors import ConfigError, WalgreensApiError
from .models import (
    CouponResult,
    OrderProduct,
    OrderSubmission,
    UploadCredentials,
    parse_order_statuses,
    parse_products,
    parse_stores,
)

RATE_LIMITS_PER_MINUTE = {
    "creds": 300,
    "products": 300,
    "coupon": 100,
    "store": 300,
    "submit": 300,
    "status": 300,
}

MAX_DISTINCT_IMAGES = 200
MAX_QTY_PER_IMAGE = 20


class WalgreensClient:
    """A session-bound client for one Walgreens affiliate account."""

    def __init__(self, config, session=None):
        if isinstance(config, Config):
            self.config = config
        else:  # pragma: no cover - defensive, tests use Config
            raise TypeError("config must be a Config instance")
        self._session = session or requests.Session()
        self._owns_session = session is None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def close(self):
        if self._owns_session:
            self._session.close()

    # -- internals -----------------------------------------------------

    def _post(self, path, payload):
        url = self.config.base_url + path
        try:
            response = self._session.post(
                url,
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=self.config.timeout,
            )
        except requests.RequestException as exc:
            raise WalgreensApiError(f"Request to {path} failed: {exc}") from exc
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
            raise WalgreensApiError(
                f"Walgreens API returned HTTP {response.status_code} for {path}.",
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

    def _base_payload(self, app_ver=None, dev_inf=None, *, require_app_ver=False):
        payload = {"apiKey": self.config.api_key, "affId": self.config.aff_id}
        resolved_ver = app_ver if app_ver is not None else self.config.app_ver
        resolved_inf = dev_inf if dev_inf is not None else self.config.dev_inf
        if require_app_ver and (resolved_ver is None or resolved_inf is None):
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
        data = self._post("/api/photo/creds/v3", payload)
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
        data = self._post("/api/photo/products/v3", payload)
        return parse_products(data)

    def validate_coupon(self, coupon_code, product_details, *, app_ver=None, dev_inf=None):
        """Validate a coupon (``/api/photo/order/coupon/v3``).

        ``product_details`` is a list of ``{"productId": ..., "qty": ...}``
        mappings. Only add the coupon to a submit request after a
        successful validation.
        """
        payload = self._base_payload(app_ver, dev_inf, require_app_ver=True)
        payload["couponCode"] = coupon_code
        payload["act"] = "getdiscount"
        payload["productDetails"] = [_product_qty_payload(d) for d in product_details]
        data = self._post("/api/photo/order/coupon/v3", payload)
        return CouponResult.from_dict(data)

    def find_stores(self, latitude, longitude, product_details, *, app_ver=None, dev_inf=None):
        """Find photo stores near a location (``/api/photo/store/v3``).

        ``latitude``/``longitude`` may be strings or numbers; they are
        sent as strings, as in the API examples. Returns stores in the
        order the API returned them. A store whose ``promise_time`` is
        ``01-01-3000 00:00 AM`` is in the API's no-promise-time state
        (see ``PhotoStore.is_no_promise_time``).
        """
        payload = self._base_payload(app_ver, dev_inf, require_app_ver=True)
        payload["latitude"] = str(latitude)
        payload["longitude"] = str(longitude)
        payload["act"] = "photoStores"
        payload["productDetails"] = [_product_qty_payload(d) for d in product_details]
        data = self._post("/api/photo/store/v3", payload)
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
        data = self._post("/api/photo/order/submit/v3", payload)
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
        it must redact ``apiKey`` first.
        """
        products = [_coerce_order_product(d) for d in product_details]
        distinct_images = sum(p.distinct_image_count() for p in products)
        if distinct_images > MAX_DISTINCT_IMAGES:
            raise ValueError(
                f"Order has {distinct_images} distinct images; "
                f"the API allows at most {MAX_DISTINCT_IMAGES}."
            )
        for product in products:
            for image in product.image_details:
                try:
                    qty = int(image.qty)
                except (TypeError, ValueError):
                    raise ValueError(f"Image qty must be an integer, got {image.qty!r}.") from None
                if qty > MAX_QTY_PER_IMAGE:
                    raise ValueError(
                        f"Image qty {qty} exceeds the API limit of "
                        f"{MAX_QTY_PER_IMAGE} prints per image URL."
                    )
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
        data = self._post("/api/photo/order/status/v3", payload)
        return parse_order_statuses(data)


def _product_qty_payload(detail):
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
        from .models import ImageDetail

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
    raw = response.headers.get("Retry-After") if hasattr(response, "headers") else None
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None
