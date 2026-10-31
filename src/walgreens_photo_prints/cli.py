"""Command-line interface for the Walgreens Photo Prints API v3.

Configuration comes from the environment (or a ``.env`` file) and can
be overridden with flags. Credentials are never printed: JSON output
redacts ``apiKey`` wherever a payload is shown.

``submit`` places a real order. Without ``--confirm`` it only prints
the redacted payload and exits with status 2, so an order is never
placed by accident. With ``--confirm`` the caller asserts the
customer took the required terms action (``--accept-terms``).
"""

import argparse
import dataclasses
import json
import sys
from dataclasses import asdict

from ._version import __version__ as VERSION
from .client import WalgreensClient
from .config import Config, ConfigError
from .errors import WalgreensApiError
from .upload import build_upload_url, upload_image_for_credentials


def _print_json(value):
    print(json.dumps(value, indent=2, default=str))


def _redact(payload):
    redacted = dict(payload)
    if "apiKey" in redacted:
        redacted["apiKey"] = "***"
    return redacted


def _load_json_file(path):
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as exc:
        raise ValueError(f"Cannot read JSON file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
    return data


def _product_qty_details(data):
    if not isinstance(data, list):
        raise ValueError("Product details JSON must be a list.")
    details = []
    for entry in data:
        if not isinstance(entry, dict) or "productId" not in entry or "qty" not in entry:
            raise ValueError(f"Each product detail needs productId and qty, got {entry!r}.")
        details.append({"productId": str(entry["productId"]), "qty": str(entry["qty"])})
    return details


def _order_products(data):
    if not isinstance(data, list):
        raise ValueError("Order product details JSON must be a list.")
    products = []
    for entry in data:
        if not isinstance(entry, dict) or "productId" not in entry:
            raise ValueError(f"Each order product needs productId, got {entry!r}.")
        images = entry.get("imageDetails", [])
        if not isinstance(images, list) or not images:
            raise ValueError(f"Order product {entry['productId']!r} needs imageDetails.")
        products.append(
            {
                "productId": str(entry["productId"]),
                "imageDetails": [
                    {"url": str(i["url"]), "qty": str(i.get("qty", "1"))} for i in images
                ],
                **(
                    {"multiImageQuantity": str(entry["multiImageQuantity"])}
                    if entry.get("multiImageQuantity") is not None
                    else {}
                ),
            }
        )
    return products


def _add_config_args(parser):
    parser.add_argument("--api-key", default=None, help="Walgreens API key (or WALGREENS_API_KEY).")
    parser.add_argument("--aff-id", default=None, help="Affiliate ID (or WALGREENS_AFF_ID).")
    parser.add_argument("--base-url", default=None, help="API base URL (or WALGREENS_BASE_URL).")
    parser.add_argument("--app-ver", default=None, help="App version (or WALGREENS_APP_VER).")
    parser.add_argument("--dev-inf", default=None, help="Device info (or WALGREENS_DEV_INF).")
    parser.add_argument(
        "--platform", default=None, help="Platform, default ios (or WALGREENS_PLATFORM)."
    )
    parser.add_argument("--timeout", type=float, default=None, help="Request timeout in seconds.")
    parser.add_argument("--env-file", default=None, help="Load variables from this .env file.")


def _config_from_args(args):
    config = Config.from_env(env_file=args.env_file)
    overrides = {
        field: value
        for field, value in (
            ("api_key", args.api_key),
            ("aff_id", args.aff_id),
            ("base_url", args.base_url),
            ("app_ver", args.app_ver),
            ("dev_inf", args.dev_inf),
            ("platform", args.platform),
            ("timeout", args.timeout),
        )
        if value is not None
    }
    # dataclasses.replace re-runs Config validation, and a future
    # Config field is picked up here automatically.
    return dataclasses.replace(config, **overrides) if overrides else config


def build_parser():
    parser = argparse.ArgumentParser(
        prog="walgreens-prints",
        description="Client for the Walgreens Native Photo Prints API v3.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("creds", help="Fetch upload credentials.")
    _add_config_args(p)

    p = sub.add_parser("products", help="List products and prices.")
    _add_config_args(p)
    p.add_argument("--product-group-id", default=None)

    p = sub.add_parser("coupon", help="Validate a coupon code.")
    _add_config_args(p)
    p.add_argument("--code", required=True)
    p.add_argument("--product-details", required=True, help="JSON file of productId/qty pairs.")

    p = sub.add_parser("stores", help="Find photo stores near a location.")
    _add_config_args(p)
    p.add_argument("--latitude", required=True)
    p.add_argument("--longitude", required=True)
    p.add_argument("--product-details", required=True, help="JSON file of productId/qty pairs.")

    p = sub.add_parser("submit", help="Submit a photo order (real order; needs --confirm).")
    _add_config_args(p)
    p.add_argument("--first-name", required=True)
    p.add_argument("--last-name", required=True)
    p.add_argument("--phone", required=True)
    p.add_argument("--email", required=True)
    p.add_argument("--store-num", required=True)
    p.add_argument("--promise-time", required=True)
    p.add_argument("--product-details", required=True, help="JSON file of order products.")
    p.add_argument("--coupon-code", default=None)
    p.add_argument("--publisher-id", default=None)
    p.add_argument("--aff-notes", default=None)
    p.add_argument("--accept-terms", action="store_true", help="Customer took the terms action.")
    p.add_argument("--confirm", action="store_true", help="Actually submit the order.")

    p = sub.add_parser("status", help="Fetch order statuses by vendor order ID.")
    _add_config_args(p)
    p.add_argument("order_ids", nargs="+")

    p = sub.add_parser("upload-url", help="Fetch credentials and print one upload URL (no upload).")
    _add_config_args(p)

    p = sub.add_parser("upload", help="Upload one image via fresh credentials.")
    _add_config_args(p)
    p.add_argument("image", help="Path to a JPEG image file.")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = _config_from_args(args)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    try:
        with WalgreensClient(config) as client:
            if args.command == "creds":
                result = client.fetch_upload_credentials()
                _print_json(result.redacted_dict())
            elif args.command == "products":
                _print_json(
                    [
                        asdict(p)
                        for p in client.list_products(product_group_id=args.product_group_id)
                    ]
                )
            elif args.command == "coupon":
                details = _product_qty_details(_load_json_file(args.product_details))
                result = client.validate_coupon(args.code, details)
                _print_json({**asdict(result), "new_subtotal": result.new_subtotal})
            elif args.command == "stores":
                details = _product_qty_details(_load_json_file(args.product_details))
                stores = client.find_stores(args.latitude, args.longitude, details)
                _print_json([asdict(s) for s in stores])
            elif args.command == "submit":
                products = _order_products(_load_json_file(args.product_details))
                if not args.confirm:
                    payload = client.build_submit_payload(
                        first_name=args.first_name,
                        last_name=args.last_name,
                        phone=args.phone,
                        email=args.email,
                        store_num=args.store_num,
                        promise_time=args.promise_time,
                        product_details=products,
                        coupon_code=args.coupon_code,
                        publisher_id=args.publisher_id,
                        aff_notes=args.aff_notes,
                    )
                    _print_json(_redact(payload))
                    print(
                        "Refusing to submit without --confirm. "
                        "Re-run with --confirm --accept-terms to place this order.",
                        file=sys.stderr,
                    )
                    return 2
                if not args.accept_terms:
                    print("error: --accept-terms is required to submit an order.", file=sys.stderr)
                    return 2
                result = client.submit_order(
                    first_name=args.first_name,
                    last_name=args.last_name,
                    phone=args.phone,
                    email=args.email,
                    store_num=args.store_num,
                    promise_time=args.promise_time,
                    product_details=products,
                    coupon_code=args.coupon_code,
                    publisher_id=args.publisher_id,
                    aff_notes=args.aff_notes,
                    terms_accepted=True,
                )
                _print_json(asdict(result))
            elif args.command == "status":
                entries = client.get_order_status(args.order_ids)
                _print_json([asdict(e) for e in entries])
            elif args.command == "upload-url":
                credentials = client.fetch_upload_credentials()
                if not credentials.sas_key_token:
                    print("error: credentials response contained no sasKeyToken.", file=sys.stderr)
                    return 1
                print(build_upload_url(credentials.sas_key_token, config.aff_id))
            elif args.command == "upload":
                upload_url, status_code = upload_image_for_credentials(client, args.image)
                _print_json({"upload_url": upload_url, "status_code": status_code})
    except (ConfigError, WalgreensApiError, ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
