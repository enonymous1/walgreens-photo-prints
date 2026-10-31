"""Flask front-end for the Walgreens Photo Prints API v3.

Two modes, one codebase:

* Live mode (default): the app builds a real ``WalgreensClient``
  from the environment (see ``Config.from_env``). Credentials live
  on the server only and are never sent to the browser, except that
  an upload URL is shown to the operator who requested it, exactly
  as the CLI prints it, with the same do-not-share warning. Run
  this mode locally with your own key; it has no login, so do not
  expose it publicly.
* Demo mode (``create_app(demo=True)``): the app uses the
  fictional demo client from ``demo.py``. No network call is made
  and no credentials are needed. The freeze script uses demo mode
  only.

Submit keeps the CLI's gates in both modes: a preview page shows
the redacted payload first, and only a second POST with both
``confirm`` and ``accept_terms`` checked actually submits. In demo
mode that second POST returns a fictional order and places no
real order.

Flask is an optional ``[web]`` extra, so importing this module
requires Flask to be installed; the core library does not.
"""

import hmac
import json
import os
import secrets
import tempfile

from .client import WalgreensClient
from .config import Config, ConfigError
from .demo import (
    SAMPLE_CART_JSON,
    SAMPLE_COUPON_CODE,
    SAMPLE_LATITUDE,
    SAMPLE_LONGITUDE,
    SAMPLE_ORDER_ID,
    SAMPLE_ORDER_JSON,
    create_demo_client,
)
from .errors import WalgreensApiError
from .models import ProductQty
from .upload import build_upload_url, upload_image_for_credentials


def _parse_json(text, label):
    try:
        data = json.loads(text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON in {label}: {exc}") from None
    if not isinstance(data, list):
        raise ValueError(f"{label} must be a JSON list.")
    return data


def _parse_product_qty(text):
    details = []
    for entry in _parse_json(text, "product details"):
        if not isinstance(entry, dict) or "productId" not in entry or "qty" not in entry:
            raise ValueError(f"Each product detail needs productId and qty, got {entry!r}.")
        details.append(ProductQty(str(entry["productId"]), str(entry["qty"])))
    return details


def _parse_order_products(text):
    products = []
    for entry in _parse_json(text, "order products"):
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
            }
        )
    return products


def _parse_order_ids(text):
    ids = [part.strip() for part in str(text).replace(",", "\n").splitlines() if part.strip()]
    if not ids:
        raise ValueError("At least one vendor order ID is required.")
    return ids


def _redact(payload):
    redacted = dict(payload)
    if "apiKey" in redacted:
        redacted["apiKey"] = "***"
    return redacted


def create_app(client=None, demo=False, secret_key=None):
    """Create the Flask app.

    ``demo=True`` forces the fictional demo client, ignoring any
    passed client. Otherwise a passed client is used, or a live
    client is built from the environment.
    """
    from flask import Flask, render_template, request, session

    app = Flask(__name__)
    app.secret_key = secret_key or secrets.token_hex(32)
    if demo:
        app.config["WPP_DEMO"] = True
        app_client = create_demo_client()
    else:
        app.config["WPP_DEMO"] = False
        app_client = client if client is not None else WalgreensClient(Config.from_env())
    app.config["WPP_CLIENT"] = app_client

    def csrf_token():
        token = session.get("_csrf_token")
        if not token:
            token = secrets.token_hex(32)
            session["_csrf_token"] = token
        return token

    def check_csrf():
        submitted = request.form.get("csrf_token", "")
        expected = session.get("_csrf_token", "")
        if not submitted or not expected or not hmac.compare_digest(submitted, expected):
            raise ValueError("Invalid or missing CSRF token. Reload the form and try again.")

    @app.context_processor
    def inject_common():
        from ._version import __version__

        return {"demo": app.config["WPP_DEMO"], "csrf_token": csrf_token(), "version": __version__}

    def render_error(exc):
        status = 400 if isinstance(exc, (ValueError, ConfigError)) else 502
        if isinstance(exc, WalgreensApiError):
            status = 502
        return render_template("error.html", message=str(exc)), status

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/products", methods=["GET", "POST"])
    def products():
        group_id = request.form.get("product_group_id") or None
        try:
            if request.method == "POST":
                check_csrf()
                items = app_client.list_products(product_group_id=group_id)
            elif app.config["WPP_DEMO"]:
                items = app_client.list_products()
            else:
                items = None
        except (ValueError, ConfigError, WalgreensApiError) as exc:
            return render_error(exc)
        return render_template("products.html", products=items, group_id=group_id or "")

    @app.route("/stores", methods=["GET", "POST"])
    def stores():
        latitude = request.form.get("latitude") or ""
        longitude = request.form.get("longitude") or ""
        details_text = request.form.get("product_details") or ""
        try:
            if request.method == "POST":
                check_csrf()
                details = _parse_product_qty(details_text)
                found = app_client.find_stores(latitude, longitude, details)
            elif app.config["WPP_DEMO"]:
                latitude, longitude, details_text = (
                    SAMPLE_LATITUDE,
                    SAMPLE_LONGITUDE,
                    SAMPLE_CART_JSON,
                )
                found = app_client.find_stores(
                    latitude, longitude, _parse_product_qty(details_text)
                )
            else:
                found = None
        except (ValueError, ConfigError, WalgreensApiError) as exc:
            return render_error(exc)
        return render_template(
            "stores.html",
            stores=found,
            latitude=latitude,
            longitude=longitude,
            product_details=details_text,
        )

    @app.route("/coupon", methods=["GET", "POST"])
    def coupon():
        code = request.form.get("code") or ""
        details_text = request.form.get("product_details") or ""
        try:
            if request.method == "POST":
                check_csrf()
                result = app_client.validate_coupon(code, _parse_product_qty(details_text))
            elif app.config["WPP_DEMO"]:
                code, details_text = SAMPLE_COUPON_CODE, SAMPLE_CART_JSON
                result = app_client.validate_coupon(code, _parse_product_qty(details_text))
            else:
                result = None
        except (ValueError, ConfigError, WalgreensApiError) as exc:
            return render_error(exc)
        return render_template(
            "coupon.html", result=result, code=code, product_details=details_text
        )

    @app.route("/upload", methods=["GET", "POST"])
    def upload():
        upload_url = None
        status_code = None
        if request.method == "POST":
            try:
                check_csrf()
                uploaded = request.files.get("image")
                if uploaded is None or not uploaded.filename:
                    raise ValueError("Choose an image file to upload.")
                if app.config["WPP_DEMO"]:
                    # Demo: never PUT anywhere and never touch a
                    # real file. Show the fictional URL the demo
                    # credentials would produce.
                    credentials = app_client.fetch_upload_credentials()
                    upload_url = build_upload_url(
                        credentials.sas_key_token,
                        app_client.config.aff_id,
                        image_name=uploaded.filename,
                    )
                    status_code = 201
                else:
                    suffix = os.path.splitext(uploaded.filename)[1] or ".jpg"
                    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                        uploaded.save(tmp.name)
                        tmp_path = tmp.name
                    try:
                        upload_url, status_code = upload_image_for_credentials(app_client, tmp_path)
                    finally:
                        os.unlink(tmp_path)
            except (ValueError, ConfigError, WalgreensApiError, OSError) as exc:
                return render_error(exc)
        return render_template("upload.html", upload_url=upload_url, status_code=status_code)

    @app.route("/submit", methods=["GET", "POST"])
    def submit():
        fields = {
            name: request.form.get(name, "")
            for name in (
                "first_name",
                "last_name",
                "phone",
                "email",
                "store_num",
                "promise_time",
                "coupon_code",
                "publisher_id",
                "aff_notes",
            )
        }
        order_text = request.form.get("product_details", "")
        if request.method == "GET" and app.config["WPP_DEMO"]:
            # Demo landing page shows a prefilled form, not a
            # preview, so the freeze can render it without POSTs.
            return render_template("submit.html", fields=fields, product_details=SAMPLE_ORDER_JSON)
        if request.method == "GET":
            return render_template("submit.html", fields=fields, product_details="")
        try:
            check_csrf()
            products = _parse_order_products(order_text)
            kwargs = {
                "first_name": fields["first_name"],
                "last_name": fields["last_name"],
                "phone": fields["phone"],
                "email": fields["email"],
                "store_num": fields["store_num"],
                "promise_time": fields["promise_time"],
                "product_details": products,
                "coupon_code": fields["coupon_code"] or None,
                "publisher_id": fields["publisher_id"] or None,
                "aff_notes": fields["aff_notes"] or None,
            }
            if request.form.get("confirm") and request.form.get("accept_terms"):
                result = app_client.submit_order(terms_accepted=True, **kwargs)
                return render_template("submit_result.html", result=result)
            payload = app_client.build_submit_payload(**kwargs)
        except (ValueError, ConfigError, WalgreensApiError) as exc:
            return render_error(exc)
        # Preview only: nothing has been submitted.
        return render_template(
            "submit_preview.html",
            payload=_redact(payload),
            fields=fields,
            product_details=order_text,
        )

    @app.route("/status", methods=["GET", "POST"])
    def status():
        ids_text = request.form.get("order_ids") or ""
        try:
            if request.method == "POST":
                check_csrf()
                entries = app_client.get_order_status(_parse_order_ids(ids_text))
            elif app.config["WPP_DEMO"]:
                ids_text = SAMPLE_ORDER_ID
                entries = app_client.get_order_status([SAMPLE_ORDER_ID])
            else:
                entries = None
        except (ValueError, ConfigError, WalgreensApiError) as exc:
            return render_error(exc)
        return render_template("status.html", entries=entries, order_ids=ids_text)

    return app
