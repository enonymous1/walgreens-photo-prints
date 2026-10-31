"""Stage 1 regression tests: validation, redaction, session handling.

All responses are mocked; no live Walgreens calls.
"""

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from email.utils import formatdate

import os

import pytest

from conftest import FakeResponse, FakeSession
from walgreens_photo_prints.client import WalgreensClient
from walgreens_photo_prints.config import Config, ConfigError
from walgreens_photo_prints.errors import WalgreensApiError
from walgreens_photo_prints.models import (
    CouponResult,
    ImageDetail,
    OrderProduct,
    UploadCredentials,
)
from walgreens_photo_prints.upload import build_upload_url, upload_image


def _order_kwargs(**overrides):
    kwargs = {
        "first_name": "A",
        "last_name": "B",
        "phone": "5555555555",
        "email": "a@example.test",
        "store_num": "211",
        "promise_time": "03-02-2020 5:15 PM",
        "product_details": [OrderProduct("1", [ImageDetail("https://example.test/x.jpg", "1")])],
    }
    kwargs.update(overrides)
    return kwargs


def test_credentials_repr_and_dict_do_not_leak_token():
    creds = UploadCredentials(
        upload_limit=5,
        sas_key_token="https://example.test/c?sig=SECRET",
        cloud=[{"sasKeyToken": "https://example.test/c?sig=SECRET"}],
    )
    assert "SECRET" not in repr(creds)
    assert "SECRET" not in str(creds.redacted_dict())
    assert creds.redacted_dict()["sas_key_token"] == "***"
    assert creds.redacted_dict()["cloud_entries"] == 1
    # asdict() ignores repr=False by design; document that it is unsafe here.
    assert "SECRET" in str(asdict(creds))


def test_upload_image_closes_created_session_but_not_passed_session(tmp_path, monkeypatch):
    image = tmp_path / "photo.png"
    image.write_bytes(b"png-data")

    class TrackingSession(FakeSession):
        def __init__(self):
            super().__init__([])
            self.closed_via_close = False

        def close(self):
            self.closed_via_close = True

    created = TrackingSession()
    monkeypatch.setattr("walgreens_photo_prints.upload.requests.Session", lambda: created)
    upload_image("https://example.test/c/x.png?sig=abc", str(image))
    assert created.closed_via_close

    passed = TrackingSession()
    upload_image("https://example.test/c/x.png?sig=abc", str(image), session=passed)
    assert not passed.closed_via_close


def test_upload_image_content_type_guessed_and_overridable(tmp_path):
    image = tmp_path / "photo.png"
    image.write_bytes(b"png-data")
    session = FakeSession([])
    upload_image("https://example.test/c/x.png?sig=abc", str(image), session=session)
    assert session.puts[0]["headers"]["Content-Type"] == "image/png"
    upload_image(
        "https://example.test/c/x.png?sig=abc",
        str(image),
        session=session,
        content_type="image/custom",
    )
    assert session.puts[1]["headers"]["Content-Type"] == "image/custom"


def test_build_upload_url_rejects_path_like_image_names():
    token = "https://example.test/c?sig=abc"
    for bad_name in ("../evil.jpg", "a/b.jpg", "a?b.jpg", "  spaced.jpg", "spaced.jpg  "):
        with pytest.raises(ValueError):
            build_upload_url(token, "test-aff", image_name=bad_name)


def test_submit_qty_validation_rejects_bad_values(make_client):
    client, session = make_client([])
    for bad_qty in ("0", "-1", "21", "1.5", "abc", 1.9, True):
        with pytest.raises(ValueError):
            client.build_submit_payload(
                **_order_kwargs(
                    product_details=[
                        OrderProduct("1", [ImageDetail("https://example.test/x.jpg", bad_qty)])
                    ]
                )
            )
    assert session.posts == []


def test_submit_requires_non_empty_fields_and_images(make_client):
    client, session = make_client([])
    for field in ("first_name", "last_name", "phone", "email", "store_num", "promise_time"):
        with pytest.raises(ValueError):
            client.build_submit_payload(**_order_kwargs(**{field: "  "}))
    with pytest.raises(ValueError):
        client.build_submit_payload(**_order_kwargs(product_details=[]))
    with pytest.raises(ValueError):
        client.build_submit_payload(**_order_kwargs(product_details=[OrderProduct("1", [])]))
    assert session.posts == []


def test_submit_distinct_urls_counted_not_entries(make_client):
    client, session = make_client([])
    # 300 entries, one distinct URL: within the 200-distinct limit.
    repeated = OrderProduct(
        "1", [ImageDetail("https://example.test/same.jpg", "1") for _ in range(300)]
    )
    assert client.build_submit_payload(**_order_kwargs(product_details=[repeated]))
    assert session.posts == []
    distinct = OrderProduct(
        "1", [ImageDetail(f"https://example.test/{i}.jpg", "1") for i in range(201)]
    )
    with pytest.raises(ValueError, match="at most 200"):
        client.build_submit_payload(**_order_kwargs(product_details=[distinct]))


def test_find_stores_validates_coordinates(make_client):
    client, session = make_client([])
    for lat, lon in (("abc", "0"), (91, 0), (-91, 0), (0, 181), (0, -181)):
        with pytest.raises(ValueError):
            client.find_stores(lat, lon, [{"productId": "1", "qty": "1"}])
    assert session.posts == []


def test_coupon_and_stores_require_product_details(make_client):
    client, session = make_client([])
    with pytest.raises(ValueError):
        client.validate_coupon("X", [])
    with pytest.raises(ValueError):
        client.find_stores(0, 0, [])
    assert session.posts == []


def test_http_error_body_is_included(make_client):
    client, _ = make_client([FakeResponse(None, status_code=500, text="errDesc: boom happened")])
    with pytest.raises(WalgreensApiError, match="boom happened"):
        client.list_products()


def test_user_agent_header_is_sent(make_client):
    client, session = make_client([FakeResponse({"products": []})])
    client.list_products()
    assert session.posts[0]["headers"]["User-Agent"].startswith("walgreens-photo-prints/")


def test_retry_after_http_date_parsed(make_client):
    future = datetime.now(timezone.utc) + timedelta(seconds=1800)
    client, _ = make_client(
        [
            FakeResponse(
                None,
                status_code=429,
                headers={"Retry-After": formatdate(future.timestamp(), usegmt=True)},
            )
        ]
    )
    with pytest.raises(WalgreensApiError) as excinfo:
        client.list_products()
    assert excinfo.value.throttled
    assert 0 < excinfo.value.retry_after <= 1800


def test_owned_client_session_is_closed(config, monkeypatch):
    session = FakeSession([FakeResponse({"products": []})])
    monkeypatch.setattr("walgreens_photo_prints.transport.requests.Session", lambda: session)
    with WalgreensClient(config) as client:
        client.list_products()
    assert session.closed


def test_config_timeout_none_and_platform_stripping():
    with pytest.raises(ConfigError):
        Config(api_key="k", aff_id="a", timeout=None)
    config = Config(api_key="k", aff_id="a", platform="  ios  ", app_ver=" 1.0 ", dev_inf=" d ")
    assert config.platform == "ios"
    assert config.app_ver == "1.0"
    assert config.dev_inf == "d"


def test_config_is_sandbox_uses_hostname():
    assert Config(api_key="k", aff_id="a").is_sandbox
    assert not Config(
        api_key="k", aff_id="a", base_url="https://services-qa.walgreens.com.evil.test"
    ).is_sandbox


def test_from_env_custom_mapping_sees_dotenv_without_mutating_os_environ(tmp_path, monkeypatch):
    env_file = tmp_path / "custom.env"
    env_file.write_text("WALGREENS_API_KEY=file-key\nWALGREENS_AFF_ID=file-aff\n", encoding="utf-8")
    monkeypatch.delenv("WALGREENS_API_KEY", raising=False)
    config = Config.from_env(env={"WALGREENS_AFF_ID": "mapping-aff"}, env_file=str(env_file))
    assert config.api_key == "file-key"
    assert config.aff_id == "mapping-aff"
    assert "WALGREENS_API_KEY" not in os.environ


def test_coupon_decimal_properties():
    result = CouponResult.from_dict(
        {"orderTotalPrice": 40.00, "orderDiscountPrice": 8.00, "status": "success"}
    )
    assert result.new_subtotal_decimal == Decimal("32.0")
    assert result.total_as_decimal == Decimal("40.0")
