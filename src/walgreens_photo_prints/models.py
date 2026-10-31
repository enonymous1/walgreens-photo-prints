"""Typed views over Walgreens Photo Prints API responses.

The API returns JSON objects whose fields may be absent or null. These
models keep the raw value when it is present, use ``None`` for a missing
or null field, and never invent a value. Collections are returned in the
order the API returned them; this package never sorts them. That order
is meaningful for stores in particular: the API's order is the vendor's
ordering, and sorting it would change which store a caller picks first.

Nullable-field filtering: list parsers drop only entries that are
missing the one field that makes them usable (``productId`` for
products, ``photoStoreDetails`` for stores). That filter is named and
tested, so a null elsewhere never silently becomes a wrong answer.
"""

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation


def _as_str(value):
    if value is None:
        return None
    return str(value)


def _as_decimal(value):
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _as_float(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class Product:
    """One photo product, as returned by ``/api/photo/products/v3``."""

    product_id: str
    product_desc: str | None = None
    product_size: str | None = None
    product_group_id: str | None = None
    product_price: str | None = None
    box_qty: str | None = None
    offset_width: str | None = None
    offset_height: str | None = None
    dpi: str | None = None
    multi_image_indicator: str | None = None
    res_width: str | None = None
    res_height: str | None = None
    template_url: str | None = None
    portrait_template_url: str | None = None
    vendor_qty_limit: str | None = None
    wood_frame_color: str | None = None
    backer_board_color: str | None = None

    @classmethod
    def from_dict(cls, data):
        return cls(
            product_id=_as_str(data.get("productId")),
            product_desc=_as_str(data.get("productDesc")),
            product_size=_as_str(data.get("productSize")),
            product_group_id=_as_str(data.get("productGroupId")),
            product_price=_as_str(data.get("productPrice")),
            box_qty=_as_str(data.get("boxQty")),
            offset_width=_as_str(data.get("offsetWidth")),
            offset_height=_as_str(data.get("offsetHeight")),
            dpi=_as_str(data.get("dpi")),
            multi_image_indicator=_as_str(data.get("multiImageIndicator")),
            res_width=_as_str(data.get("resWidth")),
            res_height=_as_str(data.get("resHeight")),
            template_url=_as_str(data.get("templateUrl")),
            portrait_template_url=_as_str(data.get("portraitTemplateUrl")),
            vendor_qty_limit=_as_str(data.get("vendorQtyLimit")),
            wood_frame_color=_as_str(data.get("woodFrameColor")),
            backer_board_color=_as_str(data.get("backerBoardColor")),
        )

    def price_as_decimal(self):
        """Product price as a Decimal, or None when absent/unparseable."""
        if self.product_price is None:
            return None
        try:
            return Decimal(self.product_price)
        except InvalidOperation:
            return None


def filter_products_missing_id(raw_products):
    """Drop product entries with no usable ``productId``.

    Entries that are not objects, or whose ``productId`` is missing,
    null, or blank, are dropped. Every other entry is kept, in order,
    even when its other fields are null.
    """
    kept = []
    for entry in raw_products or []:
        if not isinstance(entry, dict):
            continue
        product_id = entry.get("productId")
        if product_id is None or str(product_id).strip() == "":
            continue
        kept.append(entry)
    return kept


def parse_products(payload):
    """Parse the ``products`` list of a products response, in API order."""
    if not isinstance(payload, dict):
        raise ValueError("Products response must be a JSON object.")
    return [Product.from_dict(e) for e in filter_products_missing_id(payload.get("products"))]


NO_PROMISE_TIME = "01-01-3000 00:00 AM"


@dataclass(frozen=True)
class PhotoStore:
    """One photo store, flattened from ``photoStoreDetails``."""

    store_num: str | None = None
    promise_time: str | None = None
    type: str | None = None
    zip: str | None = None
    city: str | None = None
    state: str | None = None
    street: str | None = None
    county: str | None = None
    latitude: str | None = None
    longitude: str | None = None
    phone: str | None = None
    distance: str | None = None
    distance_unit: str | None = None
    open_time: str | None = None
    close_time: str | None = None
    extended_hours: str | None = None
    store_name: str | None = None
    holiday_event_name: str | None = None
    time_zone: str | None = None
    tax: str | None = None

    @classmethod
    def from_dict(cls, data):
        details = data.get("photoStoreDetails") if isinstance(data, dict) else None
        if not isinstance(details, dict):
            return None
        return cls(
            store_num=_as_str(details.get("storeNum")),
            promise_time=_as_str(details.get("promiseTime")),
            type=_as_str(details.get("type")),
            zip=_as_str(details.get("zip")),
            city=_as_str(details.get("city")),
            state=_as_str(details.get("state")),
            street=_as_str(details.get("street")),
            county=_as_str(details.get("county")),
            latitude=_as_str(details.get("latitude")),
            longitude=_as_str(details.get("longitude")),
            phone=_as_str(details.get("phone")),
            distance=_as_str(details.get("distance")),
            distance_unit=_as_str(details.get("distanceUnit")),
            open_time=_as_str(details.get("openTime")),
            close_time=_as_str(details.get("closeTime")),
            extended_hours=_as_str(details.get("extendedHours")),
            store_name=_as_str(details.get("storeName")),
            holiday_event_name=_as_str(details.get("holidayEventName")),
            time_zone=_as_str(details.get("timeZone")),
            tax=_as_str(details.get("tax")),
        )

    @property
    def is_no_promise_time(self):
        """True when the store reports the API's no-promise-time sentinel."""
        return self.promise_time == NO_PROMISE_TIME


def parse_stores(payload):
    """Parse the ``photoStores`` list of a store response, in API order."""
    if not isinstance(payload, dict):
        raise ValueError("Store response must be a JSON object.")
    stores = []
    for entry in payload.get("photoStores") or []:
        store = PhotoStore.from_dict(entry)
        if store is not None:
            stores.append(store)
    return stores


@dataclass(frozen=True)
class UploadCredentials:
    """Upload credentials from ``/api/photo/creds/v3``.

    The SAS token is a live credential. It is excluded from ``repr``
    like the API key is in ``Config``, and ``asdict()`` must never be
    used on this class because ``asdict`` ignores ``repr=False``.
    Use :meth:`redacted_dict` for any serialised or printed view.
    """

    upload_limit: int | None = None
    template: str | None = None
    landing_url: str | None = None
    sas_key_token: str | None = field(default=None, repr=False)
    cloud: list = field(default_factory=list, repr=False)

    def redacted_dict(self):
        """A serialisable view of these credentials with no token in it."""
        return {
            "upload_limit": self.upload_limit,
            "template": self.template,
            "landing_url": self.landing_url,
            "sas_key_token": "***" if self.sas_key_token else None,
            "cloud_entries": len(self.cloud),
        }

    @classmethod
    def from_dict(cls, data):
        cloud = data.get("cloud") or []
        if not isinstance(cloud, list):
            cloud = []
        sas_key_token = None
        for entry in cloud:
            if isinstance(entry, dict) and entry.get("sasKeyToken"):
                sas_key_token = str(entry["sasKeyToken"])
                break
        upload_limit = data.get("uploadLimit")
        try:
            upload_limit = int(upload_limit) if upload_limit is not None else None
        except (TypeError, ValueError):
            upload_limit = None
        return cls(
            upload_limit=upload_limit,
            template=_as_str(data.get("template")),
            landing_url=_as_str(data.get("landingUrl")),
            sas_key_token=sas_key_token,
            cloud=cloud,
        )


@dataclass(frozen=True)
class CouponResult:
    """Coupon validation result from ``/api/photo/order/coupon/v3``.

    The discount is subtracted from the total: ``new_subtotal`` is
    ``order_total_price - order_discount_price`` when both are present.
    """

    status: str | None = None
    order_total_price: float | None = None
    order_discount_price: float | None = None

    @classmethod
    def from_dict(cls, data):
        return cls(
            status=_as_str(data.get("status")),
            order_total_price=_as_float(data.get("orderTotalPrice")),
            order_discount_price=_as_float(data.get("orderDiscountPrice")),
        )

    @property
    def new_subtotal(self):
        if self.order_total_price is None or self.order_discount_price is None:
            return None
        return self.order_total_price - self.order_discount_price

    @property
    def total_as_decimal(self):
        """Order total as a Decimal, or None when absent/unparseable."""
        return _as_decimal(self.order_total_price)

    @property
    def discount_as_decimal(self):
        """Order discount as a Decimal, or None when absent/unparseable."""
        return _as_decimal(self.order_discount_price)

    @property
    def new_subtotal_decimal(self):
        """Subtotal as a Decimal; prefer this over float ``new_subtotal`` for money."""
        total = self.total_as_decimal
        discount = self.discount_as_decimal
        if total is None or discount is None:
            return None
        return total - discount


@dataclass(frozen=True)
class ImageDetail:
    """One uploaded image in an order, with its print quantity."""

    url: str
    qty: str = "1"

    def __post_init__(self):
        if not self.url or not str(self.url).strip():
            raise ValueError("ImageDetail url must not be empty.")

    def to_payload(self):
        return {"qty": str(self.qty), "url": self.url}


@dataclass(frozen=True)
class OrderProduct:
    """One product line in an order submission."""

    product_id: str
    image_details: list
    multi_image_quantity: str | None = None

    def __post_init__(self):
        if not self.product_id or not str(self.product_id).strip():
            raise ValueError("OrderProduct product_id must not be empty.")

    def to_payload(self):
        payload = {
            "productId": str(self.product_id),
            "imageDetails": [d.to_payload() for d in self.image_details],
        }
        if self.multi_image_quantity is not None:
            payload["multiImageQuantity"] = str(self.multi_image_quantity)
        return payload

    def distinct_image_urls(self):
        """Distinct uploaded-image URLs in this product line."""
        return {str(image.url) for image in self.image_details}

    def distinct_image_count(self):
        """Number of distinct uploaded-image URLs in this product line."""
        return len(self.distinct_image_urls())


@dataclass(frozen=True)
class OrderSubmission:
    """Order submission result from ``/api/photo/order/submit/v3``."""

    vendor_order_id: str | None = None
    status: str | None = None

    @classmethod
    def from_dict(cls, data):
        return cls(
            vendor_order_id=_as_str(data.get("vendorOrderId")),
            status=_as_str(data.get("status")),
        )


# The reference lists code "2" twice, for both "Downloaded" and
# "Received at Store". The code alone cannot distinguish them; the
# ``orderStatus`` string in the response is authoritative. This map
# preserves the ambiguity instead of guessing.
STATUS_CODE_LABELS = {
    "0": "Submitting",
    "1": "Downloading",
    "2": "Downloaded / Received at Store",
    "3": "Ready for Pickup",
    "4": "Sold",
    "5": "Cancelled by service",
    "6": "Cancelled at store",
}


@dataclass(frozen=True)
class OrderStatusEntry:
    """One order's status from ``/api/photo/order/status/v3``."""

    order_id: str | None = None
    valid: bool = False
    code: str | None = None
    order_status: str | None = None

    @classmethod
    def from_dict(cls, data):
        valid_raw = data.get("valid")
        if isinstance(valid_raw, bool):
            valid = valid_raw
        elif isinstance(valid_raw, str):
            valid = valid_raw.strip().lower() == "true"
        else:
            valid = bool(valid_raw)
        return cls(
            order_id=_as_str(data.get("orderId")),
            valid=valid,
            code=_as_str(data.get("code")),
            order_status=_as_str(data.get("orderStatus")),
        )

    @property
    def status_label(self):
        """Label for this order's status.

        The raw ``orderStatus`` string is authoritative: code ``"2"``
        alone is ambiguous ("Downloaded" vs "Received at Store"), so
        it is only used as a fallback when the API gave no string.
        """
        if self.order_status:
            return self.order_status
        if self.code is not None:
            return STATUS_CODE_LABELS.get(self.code)
        return None


def parse_order_statuses(payload):
    """Parse the ``statuses`` list of a status response, in API order."""
    if not isinstance(payload, dict):
        raise ValueError("Order status response must be a JSON object.")
    return [
        OrderStatusEntry.from_dict(e)
        for e in (payload.get("statuses") or [])
        if isinstance(e, dict)
    ]
